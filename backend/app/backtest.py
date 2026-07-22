"""金字塔加仓策略历史回测

用基金历史净值验证加仓档位参数的有效性：
- 模拟规则：收益率（相对累计投入成本）跌破某档线且该档未触发过 → 按 ratio × 初始本金买入
- 净值口径：分红再投资（用日涨跌幅链式构建复权净值，避免分红除权造成的假跌幅）
- 对比基准：同期一次性买入持有
"""

from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger(__name__)


def backtest_pyramid_strategy(
    history: list[dict],
    initial_principal: float,
    tiers: list[dict],
    max_investment: float = 0,
) -> Optional[dict]:
    """回测金字塔加仓策略

    Args:
        history: get_fund_nav_history 返回的净值列表（最新在前），
            需包含 date / daily_change 字段，建议 ≥ 250 个交易日
        initial_principal: 初始买入金额（回测起点一次性买入）
        tiers: 加仓档位 [{"line": -8, "ratio": 5}, ...]，line 为收益率阈值(%)，ratio 为初始本金的比例(%)
        max_investment: 投入上限（0 = 无上限）

    Returns:
        回测指标 dict；数据不足（< 60 个交易日）返回 None
    """
    if initial_principal <= 0 or len(history) < 60:
        return None

    valid_tiers = sorted(
        [t for t in (tiers or []) if (t.get("ratio") or 0) > 0 and (t.get("line") or 0) < 0],
        key=lambda t: t["line"],
        reverse=True,  # 从浅到深：-8 先于 -22
    )
    if not valid_tiers:
        return None

    # 构建时间正序的复权净值序列（分红再投资口径）
    chrono = list(reversed(history))
    adj = [1.0]
    start_date = chrono[0].get("date", "")
    for h in chrono[1:]:
        try:
            chg = float(h.get("daily_change") or 0)
        except (ValueError, TypeError):
            chg = 0.0
        chg = max(chg, -99.0)  # 防脏数据
        adj.append(adj[-1] * (1 + chg / 100))
    end_date = chrono[-1].get("date", "")

    # 模拟：起点一次性买入初始本金
    shares = initial_principal / adj[0]
    invested = initial_principal
    triggered = [False] * len(valid_tiers)
    budget_cap = max_investment if max_investment > 0 else float("inf")
    curve_ratio = []  # 每日 市值/累计投入，用于算策略回撤

    for price in adj[1:]:
        ret = (shares * price - invested) / invested * 100
        for j, t in enumerate(valid_tiers):
            if not triggered[j] and ret <= t["line"]:
                amount = initial_principal * t["ratio"] / 100
                amount = min(amount, budget_cap - invested)
                if amount > 0:
                    shares += amount / price
                    invested += amount
                    triggered[j] = True
        curve_ratio.append(shares * price / invested)

    def _max_dd(series: list[float]) -> float:
        peak, mdd = series[0], 0.0
        for v in series:
            peak = max(peak, v)
            if peak > 0:
                mdd = min(mdd, (v - peak) / peak * 100)
        return round(mdd, 2)

    final_value = shares * adj[-1]
    strategy_ret = (final_value - invested) / invested * 100
    hold_ret = (adj[-1] / adj[0] - 1) * 100
    total_planned = initial_principal * (1 + sum(t["ratio"] for t in valid_tiers) / 100)

    result = {
        "days": len(adj),
        "start_date": start_date,
        "end_date": end_date,
        "trigger_count": sum(triggered),
        "tier_count": len(valid_tiers),
        "invested": round(invested, 2),
        "final_value": round(final_value, 2),
        "strategy_return": round(strategy_ret, 2),
        "hold_return": round(hold_ret, 2),
        "excess_return": round(strategy_ret - hold_ret, 2),
        "strategy_max_dd": _max_dd(curve_ratio) if curve_ratio else 0.0,
        "hold_max_dd": _max_dd(adj),
        "utilization": round(invested / total_planned * 100, 1) if total_planned > 0 else 0.0,
    }
    logger.info(
        "回测完成: %s ~ %s (%d天), 触发 %d/%d 档, 策略 %.2f%% vs 持有 %.2f%%",
        start_date, end_date, result["days"], result["trigger_count"],
        result["tier_count"], strategy_ret, hold_ret,
    )
    return result


def format_backtest_summary(bt: dict) -> str:
    """把回测结果格式化为注入 LLM prompt 的文本"""
    if not bt:
        return ""
    span = f"{bt.get('start_date', '?')} ~ {bt.get('end_date', '?')}"
    return (
        f"当前档位参数历史回测（{span}，分红再投资口径，初始一次性买入后按档位补仓）："
        f"共触发 {bt['trigger_count']}/{bt['tier_count']} 档加仓，"
        f"累计投入 ¥{bt['invested']:,.0f}，期末策略收益 {bt['strategy_return']:+.2f}%"
        f"（同期一次性持有 {bt['hold_return']:+.2f}%，超额 {bt['excess_return']:+.2f}%），"
        f"策略最大回撤 {bt['strategy_max_dd']}%（持有回撤 {bt['hold_max_dd']}%），"
        f"资金利用率 {bt['utilization']}%。"
        f"参考标准：资金利用率低于 50% 说明部分档位过深从未触发，可适当收窄档距；"
        f"策略收益明显跑输持有则说明加仓时机/比例不佳，应调整档位。"
    )
