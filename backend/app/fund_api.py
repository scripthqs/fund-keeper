"""
天天基金 API 服务层
提供基金信息查询、实时估值、历史净值拉取能力
"""

import json
import logging
import re

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
}

# 使用 httpx AsyncClient 复用连接
_client: httpx.AsyncClient | None = None


def _get_client() -> httpx.AsyncClient:
    """获取或创建 httpx 异步客户端"""
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(headers=HEADERS, timeout=15.0)
    return _client


async def query_fund_by_code(code: str) -> dict | None:
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
        失败返回 None
    """
    try:
        client = _get_client()
        url = FUND_REALTIME_URL.format(code=code)
        resp = await client.get(url)
        resp.raise_for_status()
        text = resp.text

        # 天天基金返回的是 JSONP 格式: jsonpgz({...});
        match = re.search(r"jsonpgz\((.+)\)", text, re.DOTALL)
        if not match:
            logger.warning("无法解析基金 %s 的 JSONP 响应: %s", code, text[:200])
            return None

        raw = json.loads(match.group(1))

        # 检查有效数据
        if not raw.get("name") or not raw.get("dwjz"):
            logger.warning("基金 %s 返回数据不完整: %s", code, raw)
            return None

        return {
            "code": raw.get("fundcode", code),
            "name": raw.get("name", ""),
            "date": raw.get("jzrq", ""),  # 净值日期
            "nav": float(raw.get("dwjz", 0)),  # 单位净值
            "estimated_nav": float(raw.get("gsz", 0)) if raw.get("gsz") else None,
            "estimated_change": float(raw.get("gszzl", 0)) if raw.get("gszzl") else None,
            "update_time": raw.get("gztime", ""),
        }
    except httpx.HTTPStatusError as e:
        logger.error("查询基金 %s 失败 (HTTP %s): %s", code, e.response.status_code, e)
        return None
    except Exception as e:
        logger.error("查询基金 %s 失败: %s", code, e)
        return None


async def get_fund_nav(code: str) -> float | None:
    """获取基金最新单位净值，简化接口"""
    info = await query_fund_by_code(code)
    if info:
        return info["nav"]
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


async def get_fund_nav_on_date(code: str, target_date: str) -> float | None:
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


async def get_fund_name(code: str) -> str | None:
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
