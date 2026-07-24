"""
基金 API 服务层
- 东方财富：基金信息查询、历史净值拉取
- 新浪财经：盘中实时净值估算（支付宝/蚂蚁财富同款数据源）
- 天天基金 fundgz 接口已于 2026 年停用，A 股盘中估值改用新浪接口
"""

from __future__ import annotations

import asyncio
import json
import logging
import math
import re
import socket
import ssl
from datetime import datetime, timedelta, timezone
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

# 东方财富历史净值接口（需要 Referer，仅返回已结算净值）
FUND_HISTORY_URL = "https://api.fund.eastmoney.com/f10/lsjz"
# 东方财富基金基本信息接口
FUND_INFO_URL = "http://fund.eastmoney.com/pingzhongdata/{code}.js"
# 新浪财经基金实时估值接口（支付宝/蚂蚁财富同款数据源，盘中每分钟更新）
FUND_ESTIMATE_URL = "https://stock.finance.sina.com.cn/fundInfo/api/openapi.php/FdFundService.getEstimateNetworthPic"

# 公共请求头
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Referer": "https://fund.eastmoney.com/",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}

# 使用 httpx AsyncClient 复用连接
_client: Optional[httpx.AsyncClient] = None
_client_no_verify: Optional[httpx.AsyncClient] = None


def _get_client(verify_ssl: bool = True) -> httpx.AsyncClient:
    """获取或创建 httpx 异步客户端

    Args:
        verify_ssl: 是否验证 SSL 证书。远程部署环境下可能因 CA 证书不全导致 SSL 失败。
    """
    global _client, _client_no_verify
    if not verify_ssl:
        if _client_no_verify is None or _client_no_verify.is_closed:
            _client_no_verify = httpx.AsyncClient(
                headers=HEADERS,
                timeout=httpx.Timeout(25.0, connect=10.0),
                follow_redirects=True,
                verify=False,
                trust_env=False,
            )
        return _client_no_verify
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(
            headers=HEADERS,
            timeout=httpx.Timeout(25.0, connect=10.0),
            follow_redirects=True,
            verify=True,
            trust_env=False,
        )
    return _client


async def _safe_https_request(method: str, url: str, **kwargs) -> httpx.Response:
    """安全的 HTTPS 请求：先尝试验证 SSL，失败后自动降级为不验证模式。

    部分云平台（如某些容器环境）缺少 CA 证书包，导致 SSL 握手失败。
    降级时会记录 warning 日志，不影响正常功能。
    """
    try:
        client = _get_client(verify_ssl=True)
        return await client.request(method, url, **kwargs)
    except (ssl.SSLError, ssl.SSLCertVerificationError) as e:
        logger.warning("SSL 验证失败，尝试降级为不验证模式: %s", str(e)[:200])
        logger.warning("目标URL: %s", url)
        client = _get_client(verify_ssl=False)
        return await client.request(method, url, **kwargs)


def _get_fallback_client() -> httpx.AsyncClient:
    """获取回退专用客户端（较短超时，避免二次等待过长）"""
    return httpx.AsyncClient(
        headers=HEADERS,
        timeout=httpx.Timeout(10.0, connect=5.0),
        follow_redirects=True,
        trust_env=False,
    )


class FundQueryError(Exception):
    """基金查询异常（区分不同错误类型以便路由层处理）"""
    def __init__(self, message: str, detail: str = "", recoverable: bool = True):
        super().__init__(message)
        self.detail = detail
        self.recoverable = recoverable  # 是否可重试


async def get_fund_estimate(code: str) -> dict:
    """
    从新浪财经获取基金盘中实时估值（支付宝/蚂蚁财富同款数据源）

    实时估值在返回的 networth 分时列表中（交易时段每分钟一条），取最后一条：
    - pre_nav: 估算净值（字符串，如 "1.4693"）
    - nav_pct: 估算涨跌幅百分比（字符串，如 "1.6829" 表示 +1.68%，无需换算）
    - min_time / pre_date: 估值时间与日期

    注意：顶层的 worth / worth_rate 是【上一个交易日】的收盘估值
    （worth_date 可验证），盘中读取会拿到昨天的数据，不能当作今日实时涨跌幅。

    Returns:
        {
            "estimated_nav": 1.4693,       # 盘中估算净值
            "estimated_change": 1.68,      # 估算涨跌幅 (%)
            "estimate_time": "10:22:00",   # 估值时间
            "estimate_date": "2026-07-22", # 估值日期
        }
        无实时估值数据时返回 None 值
    """
    try:
        resp = await _safe_https_request("GET", FUND_ESTIMATE_URL, params={"symbol": code})
        resp.raise_for_status()
        data = resp.json()

        if data.get("result", {}).get("status", {}).get("code") != 0:
            logger.warning("新浪估值接口返回异常: %s", data.get("result", {}).get("status"))
            return {"estimated_nav": None, "estimated_change": None, "estimate_time": "", "estimate_date": ""}

        inner = data.get("result", {}).get("data", {})
        networth_list = inner.get("networth", []) or []

        if not networth_list:
            logger.info("基金 %s 当前无实时估值数据（可能该基金不支持盘中估值）", code)
            return {"estimated_nav": None, "estimated_change": None, "estimate_time": "", "estimate_date": ""}

        # 取最新一条分时估值
        last = networth_list[-1]
        estimated_nav = None
        estimated_change = None
        try:
            pre_nav = last.get("pre_nav")
            if pre_nav:
                estimated_nav = float(pre_nav)
        except (ValueError, TypeError):
            pass
        try:
            nav_pct = last.get("nav_pct")
            if nav_pct not in (None, ""):
                estimated_change = round(float(nav_pct), 4)  # nav_pct 已是百分比，不要 ×100
        except (ValueError, TypeError):
            pass

        estimate_time = last.get("min_time", "")
        estimate_date = last.get("pre_date", "")

        logger.info("基金 %s 实时估值: nav=%s change=%s%% time=%s date=%s",
                    code, estimated_nav, estimated_change, estimate_time, estimate_date)
        return {
            "estimated_nav": estimated_nav,
            "estimated_change": estimated_change,
            "estimate_time": estimate_time,
            "estimate_date": estimate_date,
        }
    except Exception as e:
        _log_network_error("新浪估值", code, e)
        return {"estimated_nav": None, "estimated_change": None, "estimate_time": "", "estimate_date": ""}


async def query_fund_by_code(code: str) -> dict:
    """
    根据基金代码查询信息（名称、最新净值、实时估值等）

    数据来源：
    - 基金名称：东方财富
    - 最新已结算净值：东方财富历史净值接口
    - 盘中实时估值：新浪财经（支付宝/蚂蚁财富同款数据源）

    Returns:
        {
            "code": "000001",
            "name": "HFT Income Growth Equity A",
            "date": "2024-01-15",           # 净值日期（最近已结算日期）
            "nav": 1.2345,                  # 最新单位净值（已结算）
            "estimated_nav": 1.4450,        # 盘中估算净值（新浪实时估值）
            "estimated_change": 10.64,      # 估算涨跌幅 (%)（新浪实时估值）
            "estimate_suspended": False,    # 估值服务正常
            "update_time": "14:35:00",      # 估值更新时间
        }
    Raises:
        FundQueryError: 查询失败时抛出，包含详细错误描述
    """
    logger.info("正在查询基金 %s 数据...", code)

    # 获取基金名称（东方财富）
    name = await get_fund_name(code)
    if not name:
        logger.error(
            "[query_fund_by_code] 基金 %s 获取名称失败，可能原因: "
            "1)服务器无法访问 fund.eastmoney.com（海外部署常见）"
            "2)DNS 解析失败 3)基金代码无效",
            code,
        )
        raise FundQueryError(
            f"未查询到基金代码 {code} 的信息",
            detail="请确认: 1)基金代码正确 2)服务器可访问东方财富API（海外服务器可能被墙）",
            recoverable=False,
        )

    nav = 0.0
    date = ""
    update_time = ""

    # 获取历史净值（最近已结算净值）
    try:
        history = await get_fund_nav_history(code, page_size=1)
        if history and len(history) > 0:
            nav = history[0]["nav"]
            date = history[0]["date"]
            update_time = date
            logger.info("基金 %s 历史净值: nav=%s date=%s", code, nav, date)
    except Exception as e:
        _log_network_error("历史净值(query_fund)", code, e)

    # 获取实时估值（新浪财经，支付宝同款数据源）
    estimate = await get_fund_estimate(code)
    estimated_nav = estimate.get("estimated_nav")
    estimated_change = estimate.get("estimated_change")
    estimate_time = estimate.get("estimate_time", "")
    if estimate_time and not update_time:
        update_time = estimate_time
    elif estimate_time:
        update_time = estimate_time

    return {
        "code": code,
        "name": name,
        "date": date,
        "nav": nav,
        "estimated_nav": estimated_nav,
        "estimated_change": estimated_change,
        "estimate_suspended": False,
        "update_time": update_time,
    }


async def get_fund_nav(code: str) -> Optional[float]:
    """获取基金最新单位净值，简化接口"""
    try:
        info = await query_fund_by_code(code)
        return info["nav"]
    except FundQueryError:
        return None


async def get_fund_nav_history(
    code: str, page_index: int = 1, page_size: int = 30,
    start_date: str = "", end_date: str = "",
) -> list[dict]:
    """
    获取基金历史净值数据

    Returns:
        [{ "date": "2024-01-15", "nav": 1.2345, "accumulated_nav": 2.3456, "daily_change": "0.12" }, ...]
    """
    try:
        params = {
            "fundCode": code,
            "pageIndex": page_index,
            "pageSize": page_size,
        }
        if start_date:
            params["startDate"] = start_date
        if end_date:
            params["endDate"] = end_date

        resp = await _safe_https_request("GET", FUND_HISTORY_URL, params=params)
        resp.raise_for_status()
        data = resp.json()

        if data.get("ErrCode") != 0:
            logger.warning("获取基金 %s 历史净值失败: %s", code, data.get("ErrMsg"))
            return []

        items = (data.get("Data") or {}).get("LSJZList", [])
        result = []
        for item in items:
            dwjz = item.get("DWJZ")
            if dwjz in (None, ""):
                continue  # 跳过无净值日期（如QDII节假日/暂停披露），长周期拉取时常见
            try:
                nav = float(dwjz)
            except (ValueError, TypeError):
                continue
            try:
                acc_nav = float(item.get("LJJZ") or 0)
            except (ValueError, TypeError):
                acc_nav = 0.0
            result.append({
                "date": item.get("FSRQ", ""),               # 净值日期
                "nav": nav,                                  # 单位净值
                "accumulated_nav": acc_nav,                  # 累计净值
                "daily_change": item.get("JZZZL", "0"),     # 日涨幅(%)
            })
        return result
    except Exception as e:
        _log_network_error("历史净值", code, e)
        return []


async def get_fund_nav_series(code: str) -> list[dict]:
    """获取基金全量历史净值序列（东方财富 pingzhongdata，单次请求，最新在前）

    lsjz 接口单页上限 20 条，长周期数据需逐页翻取（太慢）；
    pingzhongdata 的 Data_netWorthTrend 包含成立以来全部日度数据，一次请求即可，
    供回测 / 长周期统计使用。

    Returns:
        [{ "date": "2024-01-15", "nav": 1.2345, "accumulated_nav": 2.3456, "daily_change": "0.12" }, ...]
        与 get_fund_nav_history 同构（最新在前），失败返回 []
    """
    try:
        resp = await _safe_https_request("GET", FUND_INFO_URL.format(code=code))
        resp.raise_for_status()
        text = resp.text

        def _extract_js_array(var_name: str) -> str:
            """bracket-match 提取 `var_name = [...]` 的数组字面量"""
            m = re.search(var_name + r"\s*=\s*\[", text)
            if not m:
                return ""
            depth = 0
            for i in range(m.end() - 1, len(text)):
                ch = text[i]
                if ch == "[":
                    depth += 1
                elif ch == "]":
                    depth -= 1
                    if depth == 0:
                        return text[m.end() - 1 : i + 1]
            return ""

        trend_raw = _extract_js_array("Data_netWorthTrend")
        if not trend_raw:
            logger.warning("基金 %s pingzhongdata 中未找到净值序列", code)
            return []

        trend = json.loads(trend_raw)

        # 累计净值（可选，失败则回退为单位净值）
        acc_map: dict = {}
        acc_raw = _extract_js_array("Data_ACWorthTrend")
        if acc_raw:
            try:
                for ts, val in json.loads(acc_raw):
                    d = datetime.fromtimestamp(
                        ts / 1000, tz=timezone(timedelta(hours=8))
                    ).strftime("%Y-%m-%d")
                    acc_map[d] = val
            except Exception:
                pass

        result = []
        for point in trend:
            try:
                nav = float(point.get("y") or 0)
                if nav <= 0:
                    continue
                date = datetime.fromtimestamp(
                    point["x"] / 1000, tz=timezone(timedelta(hours=8))
                ).strftime("%Y-%m-%d")
                chg = point.get("equityReturn")
                result.append({
                    "date": date,
                    "nav": nav,
                    "accumulated_nav": float(acc_map.get(date) or nav),
                    "daily_change": str(chg if chg is not None else "0"),
                })
            except (ValueError, TypeError, KeyError):
                continue
        result.reverse()  # 原序列为时间正序 → 翻转为最新在前
        if result:
            logger.info(
                "基金 %s 全量净值序列: %d 条（%s ~ %s）",
                code, len(result), result[-1]["date"], result[0]["date"],
            )
        return result
    except Exception as e:
        _log_network_error("全量净值序列", code, e)
        return []


async def get_fund_nav_on_date(code: str, target_date: str) -> Optional[float]:
    """
    获取基金在指定日期的单位净值（用于计算买入份额）

    从历史数据中查找指定日期的净值，如果没有精确匹配，
    则取最近一个小于等于该日期的净值。
    """
    # 先查最近 30 条
    history = await get_fund_nav_history(code, page_size=30)
    if not history:
        return None

    # 按日期降序排列（最新的在前）
    history.sort(key=lambda x: x["date"], reverse=True)

    best_nav = None
    for item in history:
        if item["date"] <= target_date:
            best_nav = item["nav"]
            # 如果有精确匹配，直接返回
            if item["date"] == target_date:
                return item["nav"]
            break

    # 如果 30 条还没找到，尝试翻页
    if best_nav is None and len(history) == 30:
        page = 2
        while best_nav is None and page <= 10:  # 最多查 10 页
            more = await get_fund_nav_history(code, page_index=page, page_size=30, end_date=target_date)
            if not more:
                break
            for item in more:
                if item["date"] <= target_date:
                    best_nav = item["nav"]
                    break
            if best_nav is not None:
                break
            page += 1

    return best_nav


async def get_fund_name(code: str) -> Optional[str]:
    """
    从东方财富获取基金名称（备用方案）
    从基金详情页 JS 数据中解析名称，使用较短超时避免长时间等待
    """
    try:
        async with _get_fallback_client() as client:
            url = FUND_INFO_URL.format(code=code)
            resp = await client.get(url)
            resp.raise_for_status()
            text = resp.text

            # 从 JS 文件中提取基金名称
            # var fS_name = "基金名称";
            match = re.search(r'fS_name\s*=\s*"([^"]+)"', text)
            if match:
                return match.group(1)

            match = re.search(r'var\s+fS_name\s*=\s*["\']([^"\']+)["\']', text)
            if match:
                return match.group(1)

            return None
    except Exception as e:
        _log_network_error("基金名称", code, e)
        return None


def _log_network_error(api_name: str, code: str, exc: Exception) -> None:
    """统一网络错误日志，按错误类型分类输出详细信息，便于远程部署排查"""
    exc_type = type(exc).__name__
    exc_msg = str(exc)[:300]

    if isinstance(exc, httpx.ConnectError):
        logger.error(
            "[%s] 基金 %s 连接失败(ConnectError): %s | 请检查: 1)服务器能否访问外网 2)DNS是否正常解析 3)防火墙是否拦截",
            api_name, code, exc_msg,
        )
    elif isinstance(exc, httpx.ConnectTimeout):
        logger.error(
            "[%s] 基金 %s 连接超时(ConnectTimeout): %s | 可能原因: 服务器到国内金融API网络不通或延迟极高",
            api_name, code, exc_msg,
        )
    elif isinstance(exc, httpx.ReadTimeout):
        logger.error(
            "[%s] 基金 %s 读取超时(ReadTimeout): %s | 接口响应慢，可能服务端限流",
            api_name, code, exc_msg,
        )
    elif isinstance(exc, (ssl.SSLError, ssl.SSLCertVerificationError)):
        logger.error(
            "[%s] 基金 %s SSL错误(SSL): %s | 远程环境可能缺少CA证书，可尝试设置 verify=False",
            api_name, code, exc_msg,
        )
    else:
        logger.error(
            "[%s] 基金 %s 未知错误(%s): %s",
            api_name, code, exc_type, exc_msg,
        )


async def check_network_connectivity() -> dict:
    """诊断外部 API 网络连通性，用于排查远程部署问题。

    依次测试三个外部 API 的可达性，返回各接口的连接耗时和错误信息。
    调用方：GET /api/funds/network-check
    """
    import time

    test_code = "000001"  # 用一只已知基金做测试
    results = {}
    overall = {"success": True}

    # 1) 东方财富 - 基金信息（HTTP 明文）
    try:
        async with _get_fallback_client() as client:
            t0 = time.monotonic()
            resp = await client.get(FUND_INFO_URL.format(code=test_code))
            elapsed = round((time.monotonic() - t0) * 1000)
            resp.raise_for_status()
            name_match = re.search(r'fS_name\s*=\s*"([^"]+)"', resp.text)
            results["eastmoney_info"] = {
                "reachable": True,
                "latency_ms": elapsed,
                "status": resp.status_code,
                "name": name_match.group(1) if name_match else "未解析",
                "note": f"HTTP 明文, {elapsed}ms",
            }
    except Exception as e:
        results["eastmoney_info"] = {
            "reachable": False,
            "error_type": type(e).__name__,
            "error": str(e)[:200],
            "note": "该接口走 HTTP，海外/云平台可能拦截",
        }
        overall["success"] = False

    # 2) 东方财富 - 历史净值（HTTPS）
    try:
        t0 = time.monotonic()
        resp = await _safe_https_request("GET", FUND_HISTORY_URL, params={"fundCode": test_code, "pageSize": 1})
        elapsed = round((time.monotonic() - t0) * 1000)
        resp.raise_for_status()
        data = resp.json()
        results["eastmoney_history"] = {
            "reachable": True,
            "latency_ms": elapsed,
            "status": resp.status_code,
            "has_data": data.get("ErrCode") == 0,
            "note": f"HTTPS, {elapsed}ms",
        }
    except Exception as e:
        results["eastmoney_history"] = {
            "reachable": False,
            "error_type": type(e).__name__,
            "error": str(e)[:200],
            "note": "该接口需要 HTTPS Referer，部分云平台可能SSL异常",
        }
        overall["success"] = False

    # 3) 新浪财经 - 实时估值（HTTPS）
    try:
        t0 = time.monotonic()
        resp = await _safe_https_request("GET", FUND_ESTIMATE_URL, params={"symbol": test_code})
        elapsed = round((time.monotonic() - t0) * 1000)
        results["sina_estimate"] = {
            "reachable": True if resp.status_code == 200 else False,
            "latency_ms": elapsed,
            "status": resp.status_code,
            "note": f"HTTPS, {elapsed}ms",
        }
    except Exception as e:
        results["sina_estimate"] = {
            "reachable": False,
            "error_type": type(e).__name__,
            "error": str(e)[:200],
            "note": "新浪接口，海外可能不可达",
        }
        overall["success"] = False

    # DNS 解析测试
    from urllib.parse import urlparse
    dns = {}
    for name, url in [
        ("fund.eastmoney.com", "http://fund.eastmoney.com"),
        ("api.fund.eastmoney.com", "https://api.fund.eastmoney.com"),
        ("stock.finance.sina.com.cn", "https://stock.finance.sina.com.cn"),
    ]:
        host = urlparse(url).hostname
        try:
            ip = socket.getaddrinfo(host, 443, socket.AF_INET)
            dns[name] = {"resolved": True, "ip": ip[0][4][0] if ip else "unknown"}
        except Exception as e:
            dns[name] = {"resolved": False, "error": str(e)[:200]}

    return {
        "overall": overall,
        "dns_check": dns,
        "api_check": results,
        "advice": _generate_diagnosis_advice(results, dns, overall),
    }


def _generate_diagnosis_advice(api_results: dict, dns: dict, overall: dict) -> list[str]:
    """根据诊断结果生成修复建议"""
    advice = []
    if overall["success"]:
        advice.append("所有外部API连通正常，问题可能在其他地方（请检查前端控制台和后端日志）")
        return advice

    if all(not d.get("resolved", True) for d in dns.values()):
        advice.append("DNS全部解析失败 -> 服务器可能无法访问外网，请检查服务器网络配置")

    for name, info in dns.items():
        if not info.get("resolved"):
            advice.append(f"DNS解析失败: {name} -> 服务器无法解析该域名，检查DNS配置或/etc/hosts")

    for key, info in api_results.items():
        if not info.get("reachable"):
            err_type = info.get("error_type", "")
            if "SSL" in err_type or "Certificate" in err_type:
                advice.append(f"SSL证书错误({key}): 远程环境缺少CA证书 -> 可设置 httpx 的 verify=False")
            elif "Connect" in err_type or "Timeout" in err_type:
                advice.append(f"连接超时({key}): 国内金融API从海外或云平台访问可能被墙 -> 考虑部署到国内服务器或使用代理")
            elif "ConnectError" in err_type:
                advice.append(f"连接拒绝({key}): 防火墙可能拦截了出站请求 -> 检查云平台安全组/防火墙规则")

    return advice or ["未知错误，请查看上方详细错误信息手动排查"]


# ==================== 实时市场数据（供 AI 宏观分析注入，弥补 LLM 知识截止日期） ====================

# 新浪财经指数行情接口：上证指数 / 沪深300 / 创业板指 / 深证成指
SINA_INDEX_URL = "https://hq.sinajs.cn/list=sh000001,sh000300,sz399006,sz399001"

# 中证指数官网日度行情接口（peg 字段实为市盈率 PE，每日一条）
CSINDEX_PERF_URL = "https://www.csindex.com.cn/csindex-home/perf/index-perf"

# 估值分位缓存：{index_code: {"day": "2026-07-22", "data": {...}}}，按自然日缓存（数据日频更新）
_valuation_cache: dict = {}
# 净值历史缓存：{(code, page_size): (expire_ts, data)}，TTL 10 分钟，避免 AI 推荐反复点击时重复拉取
_nav_history_cache: dict = {}
_NAV_CACHE_TTL = 600


async def get_index_pe_percentile(index_code: str, index_name: str, years: int = 10) -> dict:
    """获取指数 PE 及近 N 年百分位（中证指数官网，免费公开接口）

    百分位 = 近 N 年中有多少比例的交易日 PE 低于当前值，越高代表越贵。

    Returns:
        {"name": "沪深300", "pe": 14.53, "percentile": 78.0, "date": "20260721"}
        失败时 pe/percentile 为 None（优雅降级）
    """
    today = datetime.now().strftime("%Y-%m-%d")
    cached = _valuation_cache.get(index_code)
    if cached and cached.get("day") == today:
        return cached["data"]

    result = {"name": index_name, "pe": None, "percentile": None, "date": ""}
    try:
        end = datetime.now().strftime("%Y%m%d")
        start = (datetime.now() - timedelta(days=int(years * 365.25) + 5)).strftime("%Y%m%d")
        resp = await _safe_https_request(
            "GET", CSINDEX_PERF_URL,
            params={"indexCode": index_code, "startDate": start, "endDate": end},
            timeout=httpx.Timeout(8.0, connect=5.0),  # 估值是辅助数据，慢源快速失败不阻塞主流程
        )
        resp.raise_for_status()
        rows = (resp.json() or {}).get("data") or []
        pes = []
        for row in rows:
            try:
                if row.get("peg"):
                    pes.append(float(row["peg"]))
            except (ValueError, TypeError):
                pass
        if pes:
            cur = pes[-1]
            percentile = round(sum(1 for p in pes if p < cur) / len(pes) * 100, 1)
            result = {
                "name": index_name,
                "pe": round(cur, 2),
                "percentile": percentile,
                "date": rows[-1].get("tradeDate", ""),
            }
            logger.info("指数 %s PE=%s，近%d年分位=%s%%", index_name, cur, years, percentile)
    except Exception as e:
        logger.warning("获取指数 %s 估值分位失败: %s", index_name, e)

    _valuation_cache[index_code] = {"day": today, "data": result}
    return result


async def get_index_valuations() -> list[dict]:
    """并发获取主要宽基指数估值分位（沪深300 / 中证500）"""
    results = await asyncio.gather(
        get_index_pe_percentile("000300", "沪深300"),
        get_index_pe_percentile("000905", "中证500"),
        return_exceptions=True,
    )
    return [r for r in results if isinstance(r, dict) and r.get("pe") is not None]


async def _get_nav_history_cached(code: str, page_size: int) -> list:
    """带 10 分钟缓存的净值历史查询（仅供 AI 分析场景使用，自动更新等场景仍走实时查询）

    lsjz 接口单页上限 20 条：page_size ≤ 20 走 lsjz；
    更大跨度走 pingzhongdata 全量序列（单次请求），截取前 page_size 条。
    """
    key = (code, page_size)
    now = datetime.now().timestamp()
    cached = _nav_history_cache.get(key)
    if cached and cached[0] > now:
        return cached[1]
    if page_size > 20:
        series = await get_fund_nav_series(code)
        data = series[:page_size]
    else:
        data = await get_fund_nav_history(code, page_size=page_size)
    if data:
        _nav_history_cache[key] = (now + _NAV_CACHE_TTL, data)
    return data


async def get_index_realtime_quotes() -> list[dict]:
    """获取主要指数实时行情（新浪财经）

    Returns:
        [{"name": "上证指数", "price": 3093.7, "change_pct": 0.52}, ...]
    """
    try:
        resp = await _safe_https_request(
            "GET", SINA_INDEX_URL,
            headers={"Referer": "https://finance.sina.com.cn"},
        )
        resp.raise_for_status()
        text = resp.content.decode("gbk", errors="ignore")
        quotes = []
        for m in re.finditer(r'hq_str_\w+="([^"]*)"', text):
            fields = m.group(1).split(",")
            if len(fields) < 4 or not fields[0]:
                continue
            try:
                price = float(fields[3])
                prev_close = float(fields[2])
                if prev_close <= 0:
                    continue
                change_pct = round((price - prev_close) / prev_close * 100, 2)
                quotes.append({"name": fields[0], "price": price, "change_pct": change_pct})
            except (ValueError, TypeError):
                continue
        return quotes
    except Exception as e:
        logger.warning("获取指数实时行情失败: %s", e)
        return []


async def get_fund_realtime_context(code: str, nav_days: int = 70) -> dict:
    """汇总基金实时市场数据，供 AI 宏观分析注入 prompt

    数据来源（均为免费公开接口）：
    - 近 nav_days 个交易日净值（东方财富，10 分钟缓存）→ 近1周/1月/3月收益、年化波动率、近3月最大回撤
    - 大盘指数实时行情（新浪财经）→ 上证/沪深300/创业板/深成指当前点位与涨跌幅
    - 指数估值分位（中证指数官网，按日缓存）→ 沪深300/中证500 PE 及近10年百分位

    Args:
        nav_days: 拉取的净值历史长度，AI 推荐场景传 500（兼顾回测），默认 70

    Returns:
        {
            "code": "000001",
            "nav_date": "2026-07-21",   # 净值数据截止日期
            "stats": {"week_return": ..., "month_return": ..., ...},
            "indices": [{"name": ..., "price": ..., "change_pct": ...}],
            "valuations": [{"name": "沪深300", "pe": 14.53, "percentile": 78.0, ...}],
            "history": [...],           # 原始净值列表（供回测复用，避免二次请求）
        }
        任何一步失败都会优雅降级（对应字段为空），不抛异常
    """
    ctx: dict = {"code": code, "nav_date": "", "stats": {}, "indices": [], "valuations": [], "history": []}
    if not code or not re.fullmatch(r"\d{6}", code):
        return ctx

    history, indices, valuations = await asyncio.gather(
        _get_nav_history_cached(code, nav_days),
        get_index_realtime_quotes(),
        get_index_valuations(),
        return_exceptions=True,
    )
    ctx["indices"] = indices if isinstance(indices, list) else []
    ctx["valuations"] = valuations if isinstance(valuations, list) else []

    if isinstance(history, Exception):
        _log_network_error("实时上下文-净值历史", code, history)
        history = []
    ctx["history"] = history

    if len(history) >= 2:
        navs = [h["nav"] for h in history if h.get("nav")]  # 最新在前
        ctx["nav_date"] = history[0].get("date", "")

        stats: dict = {}

        def _ret(n: int) -> Optional[float]:
            if len(navs) > n and navs[n]:
                return round((navs[0] / navs[n] - 1) * 100, 2)
            return None

        for key, n in (("week_return", 5), ("month_return", 20), ("quarter_return", 60)):
            r = _ret(n)
            if r is not None:
                stats[key] = r

        # 近 20 日年化波动率
        changes = []
        for h in history[:20]:
            try:
                changes.append(float(h.get("daily_change") or 0))
            except (ValueError, TypeError):
                pass
        if len(changes) >= 10:
            mean = sum(changes) / len(changes)
            var = sum((c - mean) ** 2 for c in changes) / (len(changes) - 1)
            stats["volatility_annual"] = round(math.sqrt(var) * math.sqrt(252), 1)

        # 近 3 月最大回撤（净值序列转时间正序后计算 peak-to-trough）
        if len(navs) >= 2:
            seq = list(reversed(navs[:60]))
            peak, max_dd = seq[0], 0.0
            for v in seq:
                peak = max(peak, v)
                if peak > 0:
                    max_dd = min(max_dd, (v - peak) / peak * 100)
            stats["max_drawdown_3m"] = round(max_dd, 2)

        ctx["stats"] = stats

    return ctx


def format_realtime_context(ctx: dict) -> str:
    """把实时市场数据格式化为注入 LLM prompt 的文本块，无数据时返回空串"""
    if not ctx:
        return ""
    lines = []
    stats = ctx.get("stats") or {}
    if stats:
        parts = []
        if "week_return" in stats:
            parts.append(f"近1周 {stats['week_return']:+}%")
        if "month_return" in stats:
            parts.append(f"近1月 {stats['month_return']:+}%")
        if "quarter_return" in stats:
            parts.append(f"近3月 {stats['quarter_return']:+}%")
        if "volatility_annual" in stats:
            parts.append(f"年化波动率 {stats['volatility_annual']}%")
        if "max_drawdown_3m" in stats:
            parts.append(f"近3月最大回撤 {stats['max_drawdown_3m']}%")
        if parts:
            lines.append(
                f"该基金近期走势（净值截至 {ctx.get('nav_date') or '未知'}）：" + "，".join(parts)
            )
    indices = ctx.get("indices") or []
    if indices:
        parts = [f"{q['name']} {q['price']:.0f}点（今日{q['change_pct']:+}%）" for q in indices]
        lines.append("大盘实时行情：" + "；".join(parts))
    valuations = ctx.get("valuations") or []
    if valuations:
        parts = [
            f"{v['name']} PE {v['pe']}（近10年 {v['percentile']}% 分位）"
            for v in valuations
        ]
        lines.append(
            "指数估值（截至 " + (valuations[0].get("date") or "未知") + "）：" + "；".join(parts)
            + "。分位越高代表越贵：>70% 偏高估，30-70% 合理，<30% 偏低估"
        )
    return "\n".join(lines)
