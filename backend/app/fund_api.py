"""
天天基金 API 服务层
提供基金信息查询、实时估值、历史净值拉取能力
"""

from __future__ import annotations

import json
import logging
import re
import ssl
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

# 天天基金实时估值接口
FUND_REALTIME_URL = "https://fundgz.1234567.com.cn/js/{code}.js"
# 东方财富历史净值接口（需要 Referer）
FUND_HISTORY_URL = "https://api.fund.eastmoney.com/f10/lsjz"
# 东方财富基金基本信息接口
FUND_INFO_URL = "http://fund.eastmoney.com/pingzhongdata/{code}.js"

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


def _get_client() -> httpx.AsyncClient:
    """获取或创建 httpx 异步客户端（容忍 SSL 环境差异）"""
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(
            headers=HEADERS,
            timeout=httpx.Timeout(10.0, connect=5.0),
            follow_redirects=True,
            # 使用默认 SSL 验证，但 catch SSL 错误时记录详细信息
        )
    return _client


class FundQueryError(Exception):
    """基金查询异常（区分不同错误类型以便路由层处理）"""
    def __init__(self, message: str, detail: str = "", recoverable: bool = True):
        super().__init__(message)
        self.detail = detail
        self.recoverable = recoverable  # 是否可重试


async def query_fund_by_code(code: str) -> dict:
    """
    根据基金代码查询实时信息（名称、净值、估算涨幅等）

    Returns:
        {
            "code": "000001",
            "name": "HFT Income Growth Equity A",
            "date": "2024-01-15",           # 净值日期
            "nav": 1.2345,                  # 最新单位净值
            "estimated_nav": 1.2456,        # 实时估算净值
            "estimated_change": 0.90,       # 估算涨幅 (%)
            "update_time": "2024-01-15 15:00",
        }
    Raises:
        FundQueryError: 查询失败时抛出，包含详细错误描述
    """
    try:
        client = _get_client()
        url = FUND_REALTIME_URL.format(code=code)
        logger.info("正在查询基金 %s 实时数据...", code)
        resp = await client.get(url)
        resp.raise_for_status()
        text = resp.text

        # 天天基金返回的是 JSONP 格式: jsonpgz({...});
        match = re.search(r"jsonpgz\((.+)\)", text, re.DOTALL)
        if not match:
            logger.warning("无法解析基金 %s 的 JSONP 响应: %s", code, text[:200])
            raise FundQueryError(
                f"基金代码 {code} 的接口返回格式异常",
                detail="天天基金返回数据格式无法解析，可能接口有变动",
                recoverable=False,
            )

        raw = json.loads(match.group(1))

        # 检查有效数据
        if not raw.get("name") or not raw.get("dwjz"):
            logger.warning("基金 %s 返回数据不完整: %s", code, raw)
            raise FundQueryError(
                f"未查询到基金代码 {code} 的信息",
                detail="请确认基金代码是否正确",
                recoverable=False,
            )

        return {
            "code": raw.get("fundcode", code),
            "name": raw.get("name", ""),
            "date": raw.get("jzrq", ""),  # 净值日期
            "nav": float(raw.get("dwjz", 0)),  # 单位净值
            "estimated_nav": float(raw.get("gsz", 0)) if raw.get("gsz") else None,
            "estimated_change": float(raw.get("gszzl", 0)) if raw.get("gszzl") else None,
            "update_time": raw.get("gztime", ""),
        }

    except httpx.ConnectError as e:
        logger.error("查询基金 %s 网络连接失败: %s", code, e)
        raise FundQueryError(
            "无法连接到天天基金服务器",
            detail=f"网络连接失败，请检查服务器网络是否可访问外部站点。错误: {e}",
            recoverable=True,
        ) from e

    except httpx.ConnectTimeout as e:
        logger.error("查询基金 %s 连接超时: %s", code, e)
        raise FundQueryError(
            "连接天天基金服务器超时",
            detail="服务器网络可能较慢或受限，请稍后重试",
            recoverable=True,
        ) from e

    except httpx.ReadTimeout as e:
        logger.error("查询基金 %s 读取超时: %s", code, e)
        raise FundQueryError(
            "天天基金接口响应超时",
            detail="外部接口响应缓慢，请稍后重试",
            recoverable=True,
        ) from e

    except httpx.HTTPStatusError as e:
        logger.error("查询基金 %s HTTP错误 %s: %s", code, e.response.status_code, e)
        raise FundQueryError(
            f"天天基金接口返回错误 (HTTP {e.response.status_code})",
            detail=f"外部服务异常，请稍后重试",
            recoverable=True,
        ) from e

    except (ssl.SSLError, httpx.ConnectError) as e:
        logger.error("查询基金 %s SSL/连接异常: %s", code, e)
        raise FundQueryError(
            "服务器 SSL 证书验证失败",
            detail=f"服务器可能缺少必要的 CA 证书。错误: {e}",
            recoverable=False,
        ) from e

    except FundQueryError:
        raise

    except Exception as e:
        logger.error("查询基金 %s 未知错误: %s", code, e)
        raise FundQueryError(
            "查询基金数据时发生未知错误",
            detail=f"错误类型: {type(e).__name__}, 详情: {e}",
            recoverable=True,
        ) from e


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
        client = _get_client()
        params = {
            "fundCode": code,
            "pageIndex": page_index,
            "pageSize": page_size,
        }
        if start_date:
            params["startDate"] = start_date
        if end_date:
            params["endDate"] = end_date

        resp = await client.get(FUND_HISTORY_URL, params=params)
        resp.raise_for_status()
        data = resp.json()

        if data.get("ErrCode") != 0:
            logger.warning("获取基金 %s 历史净值失败: %s", code, data.get("ErrMsg"))
            return []

        items = data.get("Data", {}).get("LSJZList", [])
        result = []
        for item in items:
            result.append({
                "date": item.get("FSRQ", ""),               # 净值日期
                "nav": float(item.get("DWJZ", 0)),           # 单位净值
                "accumulated_nav": float(item.get("LJJZ", 0)),  # 累计净值
                "daily_change": item.get("JZZZL", "0"),     # 日涨幅(%)
            })
        return result
    except Exception as e:
        logger.error("获取基金 %s 历史净值失败: %s", code, e)
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
    从基金详情页 JS 数据中解析名称
    """
    try:
        client = _get_client()
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
        logger.error("获取基金 %s 名称失败: %s", code, e)
        return None
