"""
AI Agent 工具调用系统 - Function Calling

AI 可以调用这些工具来获取实时数据、执行操作，而不依赖用户手动填表。
"""

import json
import logging
import re
from datetime import datetime
from typing import List, Optional

import httpx

from app.database import get_db, gen_id, now_str, today_str

logger = logging.getLogger(__name__)


# ════════════════════════════════════════════════════
# 工具定义（OpenAI Function Calling 格式）
# ════════════════════════════════════════════════════

TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "get_holdings_summary",
            "description": "获取用户所有持仓基金的概要信息，包括每只基金的名称、市值、收益率、盈亏金额、持有天数",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_fund_detail",
            "description": "获取指定基金的完整详细信息，包括加仓档位、止盈止损线、投入上限等",
            "parameters": {
                "type": "object",
                "properties": {
                    "fund_name": {"type": "string", "description": "基金名称（支持模糊匹配）"},
                },
                "required": ["fund_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "check_alerts",
            "description": "检查所有基金的止盈止损预警状态，返回哪些基金接近或已触发止盈止损线",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_trading_suggestions",
            "description": "基于当前持仓数据和止盈止损规则，给出操作建议（哪些该止盈、哪些可加仓、哪些继续持有）",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_all_nav",
            "description": "获取所有基金的最新实时净值和涨跌幅，查看当前市值变化",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_investment_config",
            "description": "获取当前投资配置（止盈线、止损线、加仓策略、仓位上限等）",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_snapshot_history",
            "description": "获取指定基金的历史快照走势数据（安全垫、回本需求、每日收益等）",
            "parameters": {
                "type": "object",
                "properties": {
                    "fund_name": {"type": "string", "description": "基金名称"},
                },
                "required": ["fund_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_operation_history",
            "description": "获取用户的买卖操作历史记录",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "execute_trade",
            "description": "执行买入或卖出操作。买入时需确保用户确认；卖出时用户输入的是份额而非金额。买入按金额申请（成交净值当晚公布后确认份额），卖出按份额申请（到账金额=份额×净值-赎回费）。",
            "parameters": {
                "type": "object",
                "properties": {
                    "fund_name": {"type": "string", "description": "基金名称"},
                    "action": {"type": "string", "enum": ["buy", "sell"], "description": "买入或卖出"},
                    "amount": {"type": "number", "description": "买入时：交易金额（元）；卖出时：可不填，用 shares 指定份额"},
                    "shares": {"type": "number", "description": "卖出时：赎回份额（份）。买入时忽略此参数"},
                    "redemption_fee": {"type": "number", "description": "卖出时：赎回费用（元），选填，默认0"},
                    "note": {"type": "string", "description": "交易备注（如：触发止盈、手动加仓等）"},
                },
                "required": ["fund_name", "action"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "add_fund_quick",
            "description": "快速添加一只新基金。AI应先收集用户提供的基金信息，然后调用此工具。至少需要名称和本金",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "基金名称"},
                    "code": {"type": "string", "description": "基金代码（6位数字），没有则填''"},
                    "principal": {"type": "number", "description": "初始本金（元）"},
                    "market_value": {"type": "number", "description": "当前市值（元），不知道则填与本金相同"},
                    "buy_amount": {"type": "number", "description": "累计买入金额（元），不知道则填与本金相同"},
                    "buy_date": {"type": "string", "description": "买入日期（YYYY-MM-DD），不填则用今天"},
                },
                "required": ["name", "principal"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_fund",
            "description": "更新已有基金的任意字段。当用户描述某只基金的最新情况或要求修改数据时调用，例如「把xx市值改成5200」「xx基金代码是005827」「xx本金调整为5000」「xx止盈线设为25%」。只需传入要修改的字段，未传字段保持不变。更新后向用户汇报变化。",
            "parameters": {
                "type": "object",
                "properties": {
                    "fund_name": {"type": "string", "description": "要修改的基金名称（支持模糊匹配）"},
                    "name": {"type": "string", "description": "新的基金名称"},
                    "fund_code": {"type": "string", "description": "基金代码（6位数字）"},
                    "initial_principal": {"type": "number", "description": "初始本金（元）"},
                    "buy_date": {"type": "string", "description": "买入日期（YYYY-MM-DD）"},
                    "total_buy_amount": {"type": "number", "description": "累计买入金额（元）"},
                    "total_sell_amount": {"type": "number", "description": "累计卖出金额（元）"},
                    "current_market_value": {"type": "number", "description": "当前市值（元）"},
                    "total_shares": {"type": "number", "description": "持有份额（份），从支付宝/天天基金查到的精确份额"},
                    "max_investment": {"type": "number", "description": "投入上限（元）"},
                    "stop_profit_line": {"type": "number", "description": "止盈线（%，如 20 表示 +20%）"},
                    "stop_loss_line": {"type": "number", "description": "止损线（%，如 -25 表示 -25%）"},
                    "stop_profit_ratio": {"type": "number", "description": "止盈卖出比例（%）"},
                    "stop_loss_ratio": {"type": "number", "description": "止损卖出比例（%）"},
                    "strategy_type": {"type": "string", "enum": ["downside", "pullback"], "description": "加仓策略：downside 越跌越买 | pullback 上涨回调加仓"},
                    "add_tiers": {"type": "array", "items": {"type": "object", "properties": {"line": {"type": "number"}, "ratio": {"type": "number"}}, "required": ["line", "ratio"]}, "description": "下跌加仓档位列表"},
                    "pullback_tiers": {"type": "array", "items": {"type": "object", "properties": {"line": {"type": "number"}, "ratio": {"type": "number"}}, "required": ["line", "ratio"]}, "description": "上涨回调加仓档位列表"},
                },
                "required": ["fund_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_health_score",
            "description": "获取持仓健康度评分，包括各基金评分和综合评分",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_trading_status",
            "description": "获取今日交易状态（是否交易日、距收盘时间等）",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_web",
            "description": "联网搜索最新信息。当用户询问基金相关的最新新闻、政策、市场动态，或需要实时信息时使用",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "搜索关键词"},
                },
                "required": ["query"],
            },
        },
    },
]


# ════════════════════════════════════════════════════
# 工具实现
# ════════════════════════════════════════════════════

def _fmt(n: float) -> str:
    """格式化金额"""
    if abs(n) >= 10000:
        return f"{n/10000:.2f}万"
    return f"{n:.2f}"


def _get_funds(user_id: str) -> List[dict]:
    """获取用户所有基金"""
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM funds WHERE user_id = ? ORDER BY created_at", (user_id,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def _get_config(user_id: str) -> dict:
    """获取用户配置"""
    conn = get_db()
    row = conn.execute(
        "SELECT data FROM config WHERE user_id = ?", (user_id,)
    ).fetchone()
    conn.close()
    if row:
        return json.loads(row["data"])
    return {}


def _find_fund(funds: List[dict], name: str) -> Optional[dict]:
    """模糊匹配基金名"""
    name_lower = name.strip().lower()
    for f in funds:
        if name_lower in f["name"].lower():
            return f
    return None


def _calc_return_rate(f: dict) -> float:
    """计算收益率"""
    buy = f["total_buy_amount"] or 0
    sell = f["total_sell_amount"] or 0
    mv = f["current_market_value"] or 0
    if buy > 0:
        return round((mv - buy + sell) / buy * 100, 2)
    return 0


def _days_held(buy_date: str) -> int:
    """计算持有天数"""
    if not buy_date:
        return 0
    try:
        bd = datetime.strptime(buy_date, "%Y-%m-%d")
        return (datetime.now() - bd).days
    except:
        return 0


# ---- 工具函数实现 ----

def tool_get_holdings_summary(user_id: str) -> str:
    """📊 持仓概览"""
    funds = _get_funds(user_id)
    if not funds:
        return "📭 当前没有任何持仓基金。你可以说「帮我添加一只基金」来开始。"

    total_market = sum(f["current_market_value"] or 0 for f in funds)
    total_buy = sum(f["total_buy_amount"] or 0 for f in funds)
    total_sell = sum(f["total_sell_amount"] or 0 for f in funds)
    total_profit = total_market - total_buy + total_sell
    total_rate = round(total_profit / total_buy * 100, 2) if total_buy > 0 else 0

    lines = [
        "📊 **持仓概览**\n",
        "| 指标 | 数值 |",
        "|------|------|",
        f"| 基金数量 | {len(funds)} 只 |",
        f"| 总市值 | ¥{_fmt(total_market)} |",
        f"| 总盈亏 | ¥{_fmt(total_profit)}（{total_rate:+.2f}%） |",
        f"| 累计买入 | ¥{_fmt(total_buy)} |",
        f"| 累计卖出 | ¥{_fmt(total_sell)} |",
        "",
        "**各基金明细：**\n",
    ]

    for f in funds:
        rate = _calc_return_rate(f)
        profit = (f["current_market_value"] or 0) - (f["total_buy_amount"] or 0) + (f["total_sell_amount"] or 0)
        emoji = "🟢" if rate > 0 else ("🔴" if rate < 0 else "⚪")
        lines.append(
            f"{emoji} **{f['name']}** | 市值 ¥{_fmt(f['current_market_value'] or 0)} "
            f"| 收益率 {rate:+.2f}% | 盈亏 ¥{_fmt(profit)} | 持有 {_days_held(f.get('buy_date',''))}天"
        )

    return "\n".join(lines)


def tool_get_fund_detail(user_id: str, fund_name: str) -> str:
    """🔍 基金详情"""
    funds = _get_funds(user_id)
    f = _find_fund(funds, fund_name)
    if not f:
        return f"❌ 未找到名为「{fund_name}」的基金。请检查名称是否正确。"

    rate = _calc_return_rate(f)
    days = _days_held(f.get("buy_date", ""))
    profit = (f["current_market_value"] or 0) - (f["total_buy_amount"] or 0) + (f["total_sell_amount"] or 0)

    lines = [
        f"🔍 **{f['name']}** 详细信息\n",
        "| 项目 | 数值 |",
        "|------|------|",
        f"| 基金代码 | {f.get('fund_code') or '未设置'} |",
        f"| 初始本金 | ¥{_fmt(f['initial_principal'] or 0)} |",
        f"| 当前市值 | ¥{_fmt(f['current_market_value'] or 0)} |",
        f"| 累计买入 | ¥{_fmt(f['total_buy_amount'] or 0)} |",
        f"| 累计卖出 | ¥{_fmt(f['total_sell_amount'] or 0)} |",
        f"| 收益率 | {rate:+.2f}% |",
        f"| 浮动盈亏 | ¥{_fmt(profit)} |",
        f"| 买入日期 | {f.get('buy_date') or '未设置'}（{days}天前） |",
        f"| 投入上限 | ¥{_fmt(f.get('max_investment') or 0)} |",
    ]

    # 加仓档位
    add_tiers = f.get("add_tiers", "")
    if add_tiers:
        try:
            tiers = json.loads(add_tiers) if isinstance(add_tiers, str) else add_tiers
            if tiers:
                lines.append(f"| 加仓策略 | {f.get('strategy_type','downside')} |")
                for t in tiers:
                    lines.append(f"| 档位 | 跌至{t.get('line','?')}% → 买入{t.get('ratio','?')}% |")
        except:
            pass

    # 止盈止损
    sp = f.get("stop_profit_line") or 0
    sl = f.get("stop_loss_line") or 0
    if sp:
        lines.append(f"| 止盈线 | +{sp}%（卖出{f.get('stop_profit_ratio', '?')}%） |")
    if sl:
        lines.append(f"| 止损线 | {sl}%（卖出{f.get('stop_loss_ratio', '?')}%） |")

    return "\n".join(lines)


def tool_check_alerts(user_id: str) -> str:
    """⚠️ 预警检查"""
    funds = _get_funds(user_id)
    cfg = _get_config(user_id)

    if not funds:
        return "📭 当前没有持仓，无需预警。"

    alerts = []
    for f in funds:
        rate = _calc_return_rate(f)
        sp_line = (f.get("stop_profit_line") or 0) or cfg.get("stopProfitLine", 0)
        sl_line = abs(f.get("stop_loss_line") or 0) or abs(cfg.get("stopLossLine", 0))

        name = f["name"]

        # 已触发止盈
        if sp_line > 0 and rate >= sp_line and rate > 0:
            alerts.append(f"🔴 **{name}** 已达止盈线！({rate:+.2f}% ≥ +{sp_line}%)，建议立即止盈")
        # 接近止盈
        elif sp_line > 0 and rate > 0 and sp_line - rate < 3:
            alerts.append(f"🟡 **{name}** 接近止盈线 ({rate:+.2f}% → +{sp_line}%)")
        # 已触发止损
        elif sl_line > 0 and rate <= -sl_line and rate < 0:
            alerts.append(f"💀 **{name}** 已达止损线！({rate:+.2f}% ≤ -{sl_line}%)，建议立即止损")
        # 接近止损
        elif sl_line > 0 and rate < 0 and abs(rate) >= sl_line - 3 and rate > -sl_line:
            alerts.append(f"🔴 **{name}** 接近止损线 ({rate:+.2f}% → -{sl_line}%)")
        # 跌幅较大
        elif rate < -10 and rate > -sl_line:
            alerts.append(f"🟡 **{name}** 跌幅较大 ({rate:+.2f}%)，建议关注")

    if not alerts:
        return "✅ **全部正常** — 所有基金均未触发预警，持仓状态健康。"

    return "⚠️ **预警提醒**\n\n" + "\n".join(alerts)


def tool_get_trading_suggestions(user_id: str) -> str:
    """💡 操作建议"""
    funds = _get_funds(user_id)
    cfg = _get_config(user_id)

    if not funds:
        return "📭 当前没有持仓。你可以说「帮我添加一只基金」来开始。"

    suggestions = []
    for f in funds:
        rate = _calc_return_rate(f)
        name = f["name"]
        sp_line = (f.get("stop_profit_line") or 0) or cfg.get("stopProfitLine", 0)

        # 止盈建议
        if sp_line > 0 and rate >= sp_line and rate > 0:
            suggestions.append(f"💰 **{name}**：已达止盈线 +{sp_line}%，建议卖出止盈")

        # 回本困难
        if rate < -15:
            recovery = round(abs(rate) / (100 + rate) * 100, 1) if rate > -100 else 999
            if recovery > 20:
                suggestions.append(f"📉 **{name}**：跌幅 {rate:+.2f}%，回本需涨 {recovery}%，建议关注是否止损")

        # 加仓机会
        add_tiers_raw = f.get("add_tiers", "")
        if add_tiers_raw:
            try:
                tiers = json.loads(add_tiers_raw) if isinstance(add_tiers_raw, str) else add_tiers_raw
                for t in tiers:
                    if rate <= t.get("line", 0):
                        suggestions.append(f"📈 **{name}**：已跌至加仓档位 {t['line']}%，可加仓 {t['ratio']}%")
                        break
            except:
                pass

        # 正常持有
        if rate > 0 and rate < sp_line:
            suggestions.append(f"✅ **{name}**：盈利 {rate:+.2f}%，继续持有观察")
        elif rate >= -10 and rate < 0:
            suggestions.append(f"⏸️ **{name}**：小幅亏损 {rate:+.2f}%，暂时持有")

    if not suggestions:
        return "当前无特别操作建议，所有基金状态正常。"

    return "💡 **操作建议**\n\n" + "\n".join(suggestions[:10])


def tool_update_all_nav(user_id: str) -> str:
    """📊 查询实时净值"""
    import asyncio
    import concurrent.futures
    from app.fund_api import query_fund_by_code

    funds = _get_funds(user_id)
    if not funds:
        return "📭 当前没有持仓，无需更新。"

    # 在已有事件循环中安全执行异步查询
    def _query(code: str):
        from app import fund_api
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(query_fund_by_code(code))

        # 用独立线程的事件循环执行，每次执行前清理缓存的 AsyncClient（它绑定旧循环）
        def _run_in_thread():
            fund_api._client = None
            fund_api._client_no_verify = None
            return asyncio.run(query_fund_by_code(code))

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(_run_in_thread).result()

    results = []
    total_old_mv = 0.0
    total_est_profit = 0.0
    has_any_estimate = False

    for f in funds:
        code = f.get("fund_code", "")
        if not code:
            results.append(f"⏭️ **{f['name']}**：未设置基金代码，跳过")
            continue

        try:
            info = _query(code)
            if info:
                old_mv = f["current_market_value"] or 0
                est_change = info.get("estimated_change")
                est_is_today = info.get("estimate_is_today", False)

                if old_mv > 0:
                    if est_change is not None and est_is_today:
                        # 与前端的 calcProfitFromChange 保持一致：
                        # change% 是相对于昨日净值的，old_mv 是当前最新市值，
                        # 所以 profit = old_mv × change / (100 + change)
                        profit = round(old_mv * est_change / (100 + est_change), 2)
                        new_mv = round(old_mv + profit, 2)
                        est_time = info.get("update_time", "")
                        time_str = f" ⏱️{est_time}" if est_time else ""
                        results.append(
                            f"{'🟢' if profit >= 0 else '🔴'} **{f['name']}**："
                            f"¥{_fmt(old_mv)} → ¥{_fmt(new_mv)} "
                            f"（{'+' if profit >= 0 else ''}{_fmt(profit)}，{est_change:+.2f}%）"
                            f"📡实时预估{time_str}"
                        )
                        total_old_mv += old_mv
                        total_est_profit += profit
                        has_any_estimate = True
                    else:
                        # 未获取到实时估值（或非今日数据），展示已结算净值，不计算预估盈亏
                        nav = info.get("nav", 0)
                        nav_date = info.get("date", "?")
                        results.append(
                            f"📊 **{f['name']}**：当前市值 ¥{_fmt(old_mv)}，"
                            f"净值 {nav}（{nav_date} 已结算）"
                        )
                else:
                    nav = info.get("nav", 0)
                    results.append(f"📊 **{f['name']}**（{info.get('name', code)}）：净值 {nav}，日期 {info.get('date','?')}")
            else:
                results.append(f"❌ **{f['name']}**：查询失败")
        except Exception as e:
            results.append(f"❌ **{f['name']}**：查询出错 - {e}")

    # 汇总总体预估盈亏（放在最前面，确保 AI 不会忽略）
    lines = ["📊 **实时净值查询**\n"]
    if has_any_estimate and total_old_mv > 0:
        total_new_mv = round(total_old_mv + total_est_profit, 2)
        total_rate = round(total_est_profit / total_old_mv * 100, 2)
        emoji = "🟢" if total_est_profit >= 0 else "🔴"
        lines.append(
            f"{emoji} **📌 总体预估**：¥{_fmt(total_old_mv)} → ¥{_fmt(total_new_mv)} "
            f"| 今日预估盈亏 {('+' if total_est_profit >= 0 else '')}{_fmt(total_est_profit)}（{total_rate:+.2f}%）\n"
        )
    lines.append("\n".join(results))

    return "\n".join(lines)


def tool_get_investment_config(user_id: str) -> str:
    """⚙️ 投资配置"""
    cfg = _get_config(user_id)

    lines = [
        "⚙️ **当前投资配置**\n",
        "| 配置项 | 数值 |",
        "|------|------|",
        f"| 投资风格 | {cfg.get('style', '未设置')} |",
        f"| 止盈触发线 | +{cfg.get('stopProfitLine', 20)}% |",
        f"| 止盈卖出比例 | {cfg.get('stopProfitRatio', 10)}% |",
        f"| 止损保护 | {'✅ 启用' if cfg.get('enableStopLoss', True) else '❌ 未启用'} |",
        f"| 止损线 | {cfg.get('stopLossLine', -25)}% |",
        f"| 止损卖出比例 | {cfg.get('stopLossRatio', 50)}% |",
        f"| 移动止盈 | {'✅ 启用(回撤>' + str(cfg.get('trailingStop',8)) + '%)' if cfg.get('useTrailingStop', True) else '❌ 未启用'} |",
        f"| 极端波动线 | ±{cfg.get('extremeVolatility', 5)}% |",
        f"| 赎回费豁免 | {cfg.get('freeDays', 7)}天 |",
        f"| 仓位上限 | {cfg.get('maxPosition', 40)}% |",
    ]

    return "\n".join(lines)


def tool_get_snapshot_history(user_id: str, fund_name: str) -> str:
    """📈 快照历史"""
    funds = _get_funds(user_id)
    f = _find_fund(funds, fund_name)
    if not f:
        return f"❌ 未找到名为「{fund_name}」的基金。"

    conn = get_db()
    rows = conn.execute(
        "SELECT date, today_change, total_return, daily_profit, safety_cushion, recovery_needed, nav "
        "FROM snapshots WHERE fund_id = ? AND user_id = ? ORDER BY date DESC LIMIT 30",
        (f["id"], user_id),
    ).fetchall()
    conn.close()

    if not rows:
        return f"📈 **{f['name']}** 暂无历史快照数据。快照会在每日自动记录。"

    lines = [f"📈 **{f['name']}** 近期走势（最近30天）\n"]
    lines.append("| 日期 | 涨跌 | 收益 | 安全垫 | 回本需涨 |")
    lines.append("|------|------|------|--------|----------|")

    for r in reversed(rows):
        change = r["today_change"] or 0
        ret = r["total_return"] or 0
        cushion = r["safety_cushion"]
        recovery = r["recovery_needed"]
        emoji = "🟢" if change > 0 else ("🔴" if change < 0 else "⚪")
        lines.append(
            f"| {r['date']} | {emoji} {change:+.2f}% | {ret:+.2f}% | "
            f"{f'{cushion:.1f}%' if cushion else '-'} | {f'{recovery:.1f}%' if recovery else '-'} |"
        )

    return "\n".join(lines)


def tool_get_operation_history(user_id: str) -> str:
    """📜 操作历史"""
    conn = get_db()
    rows = conn.execute(
        "SELECT date, fund_name, type, amount, return_rate, note FROM history "
        "WHERE user_id = ? ORDER BY created_at DESC LIMIT 20",
        (user_id,),
    ).fetchall()
    conn.close()

    if not rows:
        return "📜 暂无操作记录。"

    lines = ["📜 **操作历史**（最近20条）\n"]
    lines.append("| 日期 | 基金 | 操作 | 金额 | 收益率 |")
    lines.append("|------|------|------|------|--------|")

    for r in rows:
        t = "🟢买入" if r["type"] == "买入" or r["type"] == "buy" else "🔴卖出"
        lines.append(
            f"| {r['date']} | {r['fund_name']} | {t} | ¥{_fmt(r['amount'])} "
            f"| {r['return_rate']:+.2f}% |"
        )

    return "\n".join(lines)


def tool_execute_trade(
    user_id: str,
    fund_name: str,
    action: str,
    amount: float = 0,
    shares: float = 0,
    redemption_fee: float = 0,
    note: str = "",
) -> str:
    """💸 执行交易（份额制买卖，与 funds.py execute_action 保持一致）"""
    import asyncio
    import concurrent.futures

    funds = _get_funds(user_id)
    f = _find_fund(funds, fund_name)
    if not f:
        return f"❌ 未找到名为「{fund_name}」的基金。"

    action_cn = "买入" if action == "buy" else "卖出"
    action_type = "买入" if action == "buy" else "卖出"
    code = (f.get("fund_code") or "").strip()

    if action == "buy" and amount <= 0:
        return "❌ 买入金额必须大于0。"
    if action == "sell":
        if shares <= 0:
            return "❌ 请输入卖出份额（份）。基金赎回按份额申请，非金额。"
        current_shares = f.get("total_shares", 0) or 0
        if shares > current_shares + 0.0001:
            return f"❌ 卖出份额 {shares:.2f} 超出持仓 {current_shares:.2f} 份。"

    # 异步查询净值（在独立线程中执行）
    def _get_nav():
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(_query_nav_async(code))
        from app import fund_api
        def _run():
            fund_api._client = None
            fund_api._client_no_verify = None
            return asyncio.run(_query_nav_async(code))
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(_run).result()

    async def _query_nav_async(c):
        from app.fund_api import query_fund_by_code, get_fund_nav_on_date
        if not c:
            return 1.0, False, 1.0
        nav = 1.0
        nav_is_exact = False
        try:
            nav_on_date = await get_fund_nav_on_date(c, today_str())
            if nav_on_date and nav_on_date > 0:
                nav = nav_on_date
                nav_is_exact = True
        except Exception:
            pass
        if not nav_is_exact:
            try:
                info = await query_fund_by_code(c)
                if info.get("nav", 0) > 0:
                    nav = info["nav"]
                    logger.info("AI买入 %s: 今日净值未公布，用最新已结算净值 %.4f 估算", c, nav)
            except Exception:
                pass
        return nav, nav_is_exact, nav  # (buy_nav, is_exact, sell_nav)

    nav_result = _get_nav()
    buy_nav = nav_result[0]
    nav_is_exact = nav_result[1]
    sell_nav = nav_result[2]

    conn = get_db()
    try:
        # 旧数据初始化：份额为0但市值>0时，用最新净值反推份额
        current_shares = f.get("total_shares", 0) or 0
        if current_shares <= 0 and (f["current_market_value"] or 0) > 0 and code and sell_nav > 0:
            current_shares = round((f["current_market_value"] or 0) / sell_nav, 4)
            conn.execute(
                "UPDATE funds SET total_shares=?, yesterday_nav=? WHERE id=? AND user_id=?",
                (current_shares, sell_nav, f["id"], user_id),
            )
            logger.info("AI交易前初始化旧数据: %s 份额=%.4f, 昨日NAV=%.4f",
                        f["name"], current_shares, sell_nav)

        # 保存操作前快照（包含份额和昨日净值，支持撤单）
        snapshot_before = json.dumps({
            "total_buy_amount": f["total_buy_amount"],
            "total_sell_amount": f["total_sell_amount"],
            "current_market_value": f["current_market_value"],
            "current_return_rate": f["current_return_rate"],
            "total_shares": current_shares,
            "yesterday_nav": f.get("yesterday_nav", 0),
        }, ensure_ascii=False)

        if action == "buy":
            # 买入：金额 → 估算份额
            buy_shares = round(amount / buy_nav, 4) if buy_nav > 0 else 0
            new_shares = round(current_shares + buy_shares, 4)
            new_buy = (f["total_buy_amount"] or 0) + amount
            new_market = round(new_shares * buy_nav, 2) if new_shares > 0 and buy_nav > 0 else (f["current_market_value"] or 0) + amount

            conn.execute(
                "UPDATE funds SET total_buy_amount=?, current_market_value=?, total_shares=? WHERE id=? AND user_id=?",
                (new_buy, new_market, new_shares, f["id"], user_id),
            )
            nav_tag = "精确" if nav_is_exact else "估算(22:00纠正)"
            trade_note = (note or f"AI助手{action_cn}") + f" | {buy_shares:.2f}份 @NAV{buy_nav:.4f}({nav_tag})"
            trade_amount = amount
            trade_nav = buy_nav
        else:
            # 卖出：份额 → 估算金额
            sell_shares = shares
            estimated_amount = round(sell_shares * sell_nav, 2)
            actual_amount = max(0, round(estimated_amount - redemption_fee, 2))
            new_shares = max(0, round(current_shares - sell_shares, 4))
            new_sell = (f["total_sell_amount"] or 0) + actual_amount
            new_market = round(new_shares * sell_nav, 2) if new_shares > 0 else 0

            conn.execute(
                "UPDATE funds SET total_sell_amount=?, current_market_value=?, total_shares=? WHERE id=? AND user_id=?",
                (new_sell, new_market, new_shares, f["id"], user_id),
            )
            fee_info = f" - 费{redemption_fee:.2f}" if redemption_fee > 0 else ""
            trade_note = (note or f"AI助手{action_cn}") + f" | {sell_shares:.2f}份 @NAV{sell_nav:.4f} → ¥{actual_amount:.2f}{fee_info}"
            trade_amount = actual_amount
            trade_nav = sell_nav

        # 重新计算收益率
        updated = dict(conn.execute(
            "SELECT * FROM funds WHERE id=? AND user_id=?", (f["id"], user_id)
        ).fetchone())
        if (updated["total_buy_amount"] or 0) > 0:
            new_rate = round(
                ((updated["current_market_value"] or 0) - (updated["total_buy_amount"] or 0) + (updated["total_sell_amount"] or 0))
                / updated["total_buy_amount"] * 100, 2,
            )
            conn.execute("UPDATE funds SET current_return_rate=? WHERE id=? AND user_id=?", (new_rate, f["id"], user_id))
            updated["current_return_rate"] = new_rate

        # 记录操作历史
        history_id = gen_id()
        conn.execute(
            """INSERT INTO history (id, date, fund_name, type, amount, return_rate, note, created_at,
               snapshot_before, nav_at_action, user_id)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                history_id, today_str(), updated["name"], action_type,
                trade_amount, updated["current_return_rate"], trade_note,
                now_str(), snapshot_before, trade_nav, user_id,
            ),
        )
        conn.commit()

        return (
            f"✅ **{action_cn}成功！**\n\n"
            f"基金：{updated['name']}\n"
            f"份额变动：{current_shares:.2f} → {new_shares:.2f} 份\n"
            f"操作后市值：¥{_fmt(updated.get('current_market_value', 0))}\n"
            f"操作后收益率：{updated.get('current_return_rate', 0):+.2f}%\n"
            f"净值：{trade_nav:.4f}（{'已结算' if nav_is_exact else '估算，22:00自动纠正'}）"
        )
    except Exception as e:
        conn.rollback()
        logger.error("AI交易失败: %s", e)
        return f"❌ 交易失败：{e}"
    finally:
        conn.close()


def tool_add_fund_quick(
    user_id: str,
    name: str,
    principal: float,
    code: str = "",
    market_value: float = 0,
    buy_amount: float = 0,
    buy_date: str = "",
) -> str:
    """➕ 快速添加基金"""
    if market_value <= 0:
        market_value = principal
    if buy_amount <= 0:
        buy_amount = principal
    if not buy_date:
        buy_date = today_str()

    fid = gen_id()
    now = now_str()

    # 自动计算收益率
    total_buy = buy_amount
    total_sell = 0.0
    rate = round((market_value - total_buy + total_sell) / total_buy * 100, 2) if total_buy > 0 else 0

    conn = get_db()
    conn.execute(
        """INSERT INTO funds (id, name, fund_code, initial_principal, buy_date,
           total_buy_amount, total_sell_amount, current_market_value, current_return_rate,
           max_investment, add_tiers, strategy_type, created_at, user_id)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            fid, name, code, principal, buy_date,
            total_buy, total_sell, market_value, rate,
            principal * 2, "[]", "downside", now, user_id,
        ),
    )
    conn.commit()
    conn.close()

    return (
        f"✅ **基金添加成功！**\n\n"
        f"📛 名称：{name}\n"
        f"🔢 代码：{code or '未设置'}\n"
        f"💰 本金：¥{_fmt(principal)}\n"
        f"📊 市值：¥{_fmt(market_value)}\n"
        f"📈 收益率：{rate:+.2f}%\n"
        f"📅 买入日期：{buy_date}\n\n"
        f"提示：你可以继续问我「{name}该设置什么加仓档位」来优化策略。"
    )


def _match_fund(funds: List[dict], name: str):
    """精确优先匹配基金；多个包含匹配时返回 (None, 候选列表)，无匹配返回 (None, [])"""
    nl = name.strip().lower()
    if not nl:
        return None, []
    for f in funds:
        if f["name"].lower() == nl:
            return f, []
    partial = [f for f in funds if nl in f["name"].lower()]
    if len(partial) == 1:
        return partial[0], []
    if len(partial) > 1:
        return None, partial
    return None, []


def tool_update_fund(
    user_id: str,
    fund_name: str,
    name: Optional[str] = None,
    fund_code: Optional[str] = None,
    initial_principal: Optional[float] = None,
    buy_date: Optional[str] = None,
    total_buy_amount: Optional[float] = None,
    total_sell_amount: Optional[float] = None,
    current_market_value: Optional[float] = None,
    total_shares: Optional[float] = None,
    max_investment: Optional[float] = None,
    stop_profit_line: Optional[float] = None,
    stop_loss_line: Optional[float] = None,
    stop_profit_ratio: Optional[float] = None,
    stop_loss_ratio: Optional[float] = None,
    strategy_type: Optional[str] = None,
    add_tiers: Optional[List[dict]] = None,
    pullback_tiers: Optional[List[dict]] = None,
) -> str:
    """✏️ 更新已有基金字段（部分更新，只改传入的字段）"""
    funds = _get_funds(user_id)
    f, candidates = _match_fund(funds, fund_name)
    if not f:
        if candidates:
            hint = "、".join(c["name"] for c in candidates[:8])
            return f"❌ 「{fund_name}」匹配到多只基金：{hint}。请用更准确的名称重试。"
        if funds:
            hint = "、".join(x["name"] for x in funds[:8])
            return f"❌ 未找到名为「{fund_name}」的基金。你目前的基金有：{hint}。"
        return f"❌ 未找到名为「{fund_name}」的基金，当前没有任何持仓。可以先说「添加基金」新增。"

    # 参数名 -> DB 列名 的白名单映射（列名硬编码，值参数化，防注入）
    field_map = {
        "name": name,
        "fund_code": fund_code,
        "initial_principal": initial_principal,
        "buy_date": buy_date,
        "total_buy_amount": total_buy_amount,
        "total_sell_amount": total_sell_amount,
        "current_market_value": current_market_value,
        "total_shares": total_shares,
        "max_investment": max_investment,
        "stop_profit_line": stop_profit_line,
        "stop_loss_line": stop_loss_line,
        "stop_profit_ratio": stop_profit_ratio,
        "stop_loss_ratio": stop_loss_ratio,
        "strategy_type": strategy_type,
    }
    labels = {
        "name": "名称", "fund_code": "基金代码", "initial_principal": "初始本金",
        "buy_date": "买入日期", "total_buy_amount": "累计买入", "total_sell_amount": "累计卖出",
        "current_market_value": "当前市值", "total_shares": "持有份额", "max_investment": "投入上限",
        "stop_profit_line": "止盈线", "stop_loss_line": "止损线",
        "stop_profit_ratio": "止盈卖出比例", "stop_loss_ratio": "止损卖出比例",
        "strategy_type": "策略类型",
    }

    def _disp(v):
        if isinstance(v, (int, float)):
            return _fmt(v)
        return v if v not in (None, "") else "未设置"

    def _fmt_tiers(tiers):
        if not tiers:
            return "无"
        return " | ".join(f"{t.get('line')}%->买{t.get('ratio')}%" for t in tiers)

    updates = {}   # DB 列名 -> 值
    changes = []   # 人类可读变化

    for col, val in field_map.items():
        if val is None:
            continue
        old = f.get(col)
        updates[col] = val
        changes.append(f"{labels.get(col, col)}：{_disp(old)} -> {_disp(val)}")

    # JSON 档位字段单独处理
    if add_tiers is not None:
        try:
            old_tiers = json.loads(f.get("add_tiers", "") or "[]")
        except (json.JSONDecodeError, TypeError):
            old_tiers = []
        updates["add_tiers"] = json.dumps(add_tiers, ensure_ascii=False)
        changes.append(f"加仓档位：{_fmt_tiers(old_tiers)} -> {_fmt_tiers(add_tiers)}")
    if pullback_tiers is not None:
        try:
            old_tiers = json.loads(f.get("pullback_tiers", "") or "[]")
        except (json.JSONDecodeError, TypeError):
            old_tiers = []
        updates["pullback_tiers"] = json.dumps(pullback_tiers, ensure_ascii=False)
        changes.append(f"回调加仓档位：{_fmt_tiers(old_tiers)} -> {_fmt_tiers(pullback_tiers)}")

    if not updates:
        return f"⚠️ 没有指定要更新的字段。请告诉我要修改「{f['name']}」的哪些数据（如市值、本金、代码、止盈线等）。"

    conn = get_db()
    try:
        set_clauses = ", ".join(f"{col}=?" for col in updates.keys())
        conn.execute(
            f"UPDATE funds SET {set_clauses} WHERE id=?",
            list(updates.values()) + [f["id"]],
        )

        # 涉及市值/买卖金额时自动重算收益率
        recalc = {"current_market_value", "total_buy_amount", "total_sell_amount", "initial_principal"}
        final = dict(conn.execute("SELECT * FROM funds WHERE id=?", (f["id"],)).fetchone())
        if recalc & updates.keys():
            buy = final["total_buy_amount"] or 0
            if buy > 0:
                new_rate = round(
                    ((final["current_market_value"] or 0) - buy + (final["total_sell_amount"] or 0)) / buy * 100, 2
                )
                conn.execute("UPDATE funds SET current_return_rate=? WHERE id=?", (new_rate, f["id"]))
                final["current_return_rate"] = new_rate
                changes.append(f"收益率（自动重算）：{f.get('current_return_rate', 0) or 0:+.2f}% -> {new_rate:+.2f}%")
            else:
                changes.append("⚠️ 累计买入为 0，无法计算收益率")

        conn.commit()
    except Exception as e:
        conn.rollback()
        return f"❌ 更新失败：{e}"
    finally:
        conn.close()

    return (
        f"✅ **{final['name']} 已更新！**\n\n"
        + "\n".join(f"• {c}" for c in changes)
        + f"\n\n当前市值：¥{_fmt(final['current_market_value'] or 0)} | 收益率：{final.get('current_return_rate', 0) or 0:+.2f}%"
    )


def tool_get_health_score(user_id: str) -> str:
    """💚 健康度评分"""
    funds = _get_funds(user_id)
    cfg = _get_config(user_id)

    if not funds:
        return "📭 当前没有持仓。"

    lines = ["💚 **持仓健康度**\n"]

    total_score = 0
    for f in funds:
        rate = _calc_return_rate(f)
        score = 100

        # 亏损扣分
        if rate < -20:
            score -= 40
        elif rate < -10:
            score -= 25
        elif rate < -5:
            score -= 10
        elif rate < 0:
            score -= 5

        # 接近止损扣分
        sl_line = abs(f.get("stop_loss_line") or 0) or abs(cfg.get("stopLossLine", 0))
        if sl_line > 0 and rate < 0 and abs(rate) >= sl_line - 5:
            score -= 20

        # 盈利加分
        if rate > 10:
            score += 10
        elif rate > 5:
            score += 5

        # 持有时间长加分
        days = _days_held(f.get("buy_date", ""))
        if days > 180:
            score += 5

        score = max(0, min(100, score))
        total_score += score

        emoji = "💚" if score >= 70 else ("💛" if score >= 40 else "❤️")
        lines.append(f"{emoji} **{f['name']}**：{score}分（收益率 {rate:+.2f}%）")

    avg = round(total_score / len(funds)) if funds else 0
    avg_emoji = "💚" if avg >= 70 else ("💛" if avg >= 40 else "❤️")
    lines.insert(1, f"综合评分：{avg_emoji} **{avg}/100**\n")

    return "\n".join(lines)


def tool_get_trading_status(user_id: str = "") -> str:
    """📅 交易状态"""
    from datetime import date, datetime as dt, time, timedelta

    today = date.today()
    now = dt.now()
    day_of_week = today.weekday()

    trading = day_of_week < 5
    holiday_name = ""
    try:
        from chinese_calendar import is_workday, is_holiday, get_holiday_detail
        trading = is_workday(today)
        holiday_flag = is_holiday(today)
        _, holiday_name = get_holiday_detail(today) if holiday_flag else (False, "")
    except Exception:
        pass

    if trading:
        cutoff = dt.combine(today, time(15, 0))
        remaining = max(0, int((cutoff - now).total_seconds()))
        return f"🕘 **今日可交易** — 距15:00收盘还有约 {remaining // 60} 分钟"
    else:
        next_day = today + timedelta(days=1)
        for _ in range(30):
            try:
                from chinese_calendar import is_workday
                if is_workday(next_day):
                    break
            except Exception:
                if next_day.weekday() < 5:
                    break
            next_day += timedelta(days=1)
        return f"⚪ **今日休市**{('（' + holiday_name + '）') if holiday_name else ''}，下一个交易日：{next_day.isoformat()}"


def _clean_html_text(text: str) -> str:
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"&(?:nbsp|amp|lt|gt|quot|#39);", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _parse_bing_results(html: str) -> List[dict]:
    """解析 Bing 搜索结果，返回 [{title, url, snippet}]"""
    results: List[dict] = []
    blocks = re.findall(r'<li class="b_algo"[^>]*>(.*?)</li>', html, re.DOTALL | re.IGNORECASE)
    for block in blocks[:10]:
        title_m = re.search(r"<h2[^>]*>\s*<a[^>]*href=\"([^\"]+)\"[^>]*>(.*?)</a>", block, re.DOTALL | re.IGNORECASE)
        if not title_m:
            continue
        url = title_m.group(1)
        title = _clean_html_text(title_m.group(2))
        if len(title) <= 5:
            continue
        snippet_m = re.search(
            r'class="b_caption"[^>]*>.*?<p[^>]*>(.*?)</p>',
            block,
            re.DOTALL | re.IGNORECASE,
        )
        if not snippet_m:
            snippet_m = re.search(r"<p[^>]*>(.*?)</p>", block, re.DOTALL)
        item = {"title": title, "url": url}
        if snippet_m:
            snippet = _clean_html_text(snippet_m.group(1))
            if snippet:
                item["snippet"] = snippet[:250]
        results.append(item)
    return results


def _parse_ddg_results(html: str) -> List[dict]:
    """解析 DuckDuckGo 搜索结果"""
    results: List[dict] = []
    links = re.findall(
        r'<a[^>]*class="result__a"[^>]*href=\"([^\"]+)\"[^>]*>(.*?)</a>',
        html,
        re.DOTALL | re.IGNORECASE,
    )
    snippets = re.findall(
        r'<a[^>]*class="result__snippet"[^>]*>(.*?)</a>',
        html,
        re.DOTALL | re.IGNORECASE,
    )
    for i, (url, title_html) in enumerate(links[:10]):
        title = _clean_html_text(title_html)
        if len(title) <= 5:
            continue
        item = {"title": title, "url": url}
        if i < len(snippets):
            snippet = _clean_html_text(snippets[i])
            if snippet:
                item["snippet"] = snippet[:250]
        results.append(item)
    return results


def _format_result(items: List[dict], source: str) -> str:
    """格式化搜索结果"""
    lines = [f"### {source}"]
    for i, item in enumerate(items, 1):
        title = item.get("title", "")
        url = item.get("url", "")
        snippet = item.get("snippet", "")
        lines.append(f"{i}. **[{title}]({url})**")
        if snippet:
            lines.append(f"   {snippet}")
    return "\n".join(lines)


# 金融类关键词，用于自动限定金融站点搜索
_FINANCE_KEYWORDS = [
    "基金", "股票", "A股", "港股", "美股", "大盘", "指数",
    "央行", "降准", "降息", "利率", "通胀", "GDP", "PMI",
    "行情", "涨跌", "牛市", "熊市", "回调", "反弹", "震荡",
    "政策", "监管", "证监会", "银保监", "LPR", "MLF",
    "板块", "概念", "题材", "龙头", "分红", "财报", "年报",
    "北向", "南向", "外资", "主力", "散户", "机构",
    "ETF", "LOF", "QDII", "REITs", "债券", "国债",
    "投资", "理财", "持仓", "仓位", "止损", "止盈",
    "证券", "券商", "保险", "银行", "地产", "科技",
    "新能源", "医药", "消费", "军工", "半导体", "白酒",
]


def _is_finance_query(query: str) -> bool:
    """判断是否为金融类查询"""
    return any(kw in query for kw in _FINANCE_KEYWORDS)


# 金融权威站点
_FINANCE_SITES = [
    "eastmoney.com",       # 东方财富
    "finance.sina.com.cn",  # 新浪财经
    "xueqiu.com",           # 雪球
    "cnstock.com",          # 上海证券报
    "cs.com.cn",            # 中证网
    "10jqka.com.cn",        # 同花顺
    "stcn.com",             # 证券时报
    "p5w.net",              # 全景网
    "yicai.com",            # 第一财经
    "cls.cn",               # 财联社
]


def _search_bing(query: str, headers: dict, site_filter: bool = False) -> List[dict]:
    """Bing 搜索，可选金融站点过滤"""
    if site_filter:
        site_query = " OR ".join(f"site:{s}" for s in _FINANCE_SITES[:5])
        q = f"({query}) ({site_query})"
    else:
        q = query
    try:
        resp = httpx.get(
            "https://cn.bing.com/search",
            params={"q": q, "setlang": "zh-cn", "cc": "cn", "mkt": "zh-CN"},
            headers=headers,
            timeout=15.0,
            follow_redirects=True,
        )
        if resp.status_code == 200:
            return _parse_bing_results(resp.text)
    except Exception as e:
        logger.warning("Bing search failed: %s", e)
    return []


def _fetch_sina_news(headers: dict) -> List[dict]:
    """从新浪财经获取最新快讯"""
    try:
        resp = httpx.get(
            "https://feed.mix.sina.com.cn/api/roll/get",
            params={"pageid": 153, "lid": 2509, "num": 10, "page": 1},
            headers=headers,
            timeout=10.0,
        )
        if resp.status_code == 200:
            data = resp.json()
            items = data.get("result", {}).get("data", [])
            results: List[dict] = []
            for item in items[:10]:
                title = item.get("title", "")
                url = item.get("url", "")
                intro = item.get("intro", "") or item.get("description", "")
                if title and url:
                    results.append({"title": title, "url": url, "snippet": intro[:200]})
            return results
    except Exception as e:
        logger.warning("Sina finance news failed: %s", e)
    return []


def tool_search_web(user_id: str = "", query: str = "") -> str:
    """联网搜索 - 多数据源聚合（Bing + 金融站点 + 新浪财经快讯）"""
    if not query:
        return "请提供搜索关键词"

    logger.info("联网搜索: %s", query)
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    }

    is_finance = _is_finance_query(query)
    all_results: List[dict] = []
    seen_urls: set = set()

    def add_results(items: List[dict]):
        for item in items:
            url = item.get("url", "")
            if url and url not in seen_urls:
                seen_urls.add(url)
                all_results.append(item)

    # 1. Bing 通用搜索
    bing_results = _search_bing(query, headers)
    add_results(bing_results)

    # 2. 金融类查询：金融站点限定搜索
    if is_finance:
        finance_results = _search_bing(query, headers, site_filter=True)
        add_results(finance_results)

    # 3. 金融类查询：新浪财经快讯
    if is_finance:
        sina_results = _fetch_sina_news(headers)
        add_results(sina_results)

    if not all_results:
        # DuckDuckGo 兜底
        try:
            resp = httpx.get(
                "https://html.duckduckgo.com/html/",
                params={"q": query, "kl": "cn-zh"},
                headers=headers,
                timeout=15.0,
                follow_redirects=True,
            )
            if resp.status_code == 200:
                ddg_results = _parse_ddg_results(resp.text)
                add_results(ddg_results)
        except Exception as e:
            logger.warning("DuckDuckGo search failed: %s", e)

    if not all_results:
        return f"搜索「{query}」暂无结果，请稍后重试或换个关键词"

    # 格式化输出：标题 + URL + 摘要
    lines = [f"**搜索: {query}**"]
    if is_finance:
        lines.append(f"*（已自动聚合 Bing 通用搜索 + 金融权威站点 + 新浪财经快讯，共 {len(all_results)} 条结果）*\n")
    for i, item in enumerate(all_results[:12], 1):
        title = item.get("title", "")
        url = item.get("url", "")
        snippet = item.get("snippet", "")
        lines.append(f"{i}. **[{title}]({url})**")
        if snippet:
            lines.append(f"   {snippet}")
    return "\n".join(lines)


TOOL_MAP = {
    "get_holdings_summary": tool_get_holdings_summary,
    "get_fund_detail": tool_get_fund_detail,
    "check_alerts": tool_check_alerts,
    "get_trading_suggestions": tool_get_trading_suggestions,
    "update_all_nav": tool_update_all_nav,
    "get_investment_config": tool_get_investment_config,
    "get_snapshot_history": tool_get_snapshot_history,
    "get_operation_history": tool_get_operation_history,
    "execute_trade": tool_execute_trade,
    "add_fund_quick": tool_add_fund_quick,
    "update_fund": tool_update_fund,
    "get_health_score": tool_get_health_score,
    "get_trading_status": tool_get_trading_status,
    "search_web": tool_search_web,
}


def execute_tool(tool_name: str, arguments: dict, user_id: str) -> str:
    """执行工具调用并返回结果文本"""
    func = TOOL_MAP.get(tool_name)
    if not func:
        return f"❌ 未知工具：{tool_name}"

    try:
        if "user_id" in func.__code__.co_varnames[:func.__code__.co_argcount]:
            return func(user_id=user_id, **arguments)
        else:
            return func(**arguments)
    except TypeError as e:
        logger.error(f"工具调用参数错误: {tool_name}({arguments}) -> {e}")
        return f"❌ 参数错误：{e}"
    except Exception as e:
        logger.error(f"工具执行失败: {tool_name} -> {e}")
        return f"❌ 执行失败：{e}"
