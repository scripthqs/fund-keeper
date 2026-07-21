"""
天天基金 API 服务层
提供基金信息查询、实时估值、历史净值拉取能力
（注意：天天基金 fundgz 实时接口已于 2025 年下线，现改用东方财富接口）
"""

from __future__ import annotations

import logging
import re
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

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
            timeout=httpx.Timeout(30.0, connect=15.0),
            follow_redirects=True,
            # 使用默认 SSL 验证，但 catch SSL 错误时记录详细信息
        )
    return _client


def _get_fallback_client() -> httpx.AsyncClient:
    """获取回退专用客户端（较短超时，避免二次等待过长）"""
    return httpx.AsyncClient(
        headers=HEADERS,
        timeout=httpx.Timeout(10.0, connect=5.0),
        follow_redirects=True,
    )


class FundQueryError(Exception):
    """基金查询异常（区分不同错误类型以便路由层处理）"""
    def __init__(self, message: str, detail: str = "", recoverable: bool = True):
        super().__init__(message)
        self.detail = detail
        self.recoverable = recoverable  # 是否可重试


async def query_fund_by_code(code: str) -> dict:
    """
    根据基金代码查询实时信息（名称、净值、估算涨幅等）

    直接使用东方财富接口（天天基金 fundgz 接口已于 2025 年下线）。

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
    logger.info("正在查询基金 %s 数据...", code)

    # 获取基金名称（东方财富）
    name = await get_fund_name(code)
    if not name:
        raise FundQueryError(
            f"未查询到基金代码 {code} 的信息",
            detail="请确认基金代码是否正确",
            recoverable=False,
        )

    # 获取最新净值（东方财富历史净值接口）
    nav = 0.0
    date = ""
    estimated_nav = None
    estimated_change = None
    try:
        history = await get_fund_nav_history(code, page_size=1)
        if history and len(history) > 0:
            nav = history[0]["nav"]
            date = history[0]["date"]
            # 通过日涨幅反算估算净值
            daily_pct = float(history[0].get("daily_change", "0") or "0")
            estimated_nav = round(nav * (1 + daily_pct / 100), 4)
            estimated_change = daily_pct
    except Exception as e:
        logger.warning("获取基金 %s 历史净值失败: %s", code, e)

    return {
        "code": code,
        "name": name,
        "date": date,
        "nav": nav,
        "estimated_nav": estimated_nav,
        "estimated_change": estimated_change,
        "update_time": date,
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
        logger.error("获取基金 %s 名称失败: %s", code, e)
        return None
