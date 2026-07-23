"""
策略推荐 & 操作评估 & 组合分析。
"""

import json
import logging
from typing import Optional

from ._common import (
    _get_client,
    _call_llm_with_retry,
    _call_llm_stream,
    _safe_parse_json,
    _brute_parse_json,
    TIER_RECOMMEND_PROMPT,
    EVALUATE_OPERATION_PROMPT,
    OVERALL_ANALYSIS_PROMPT,
    _build_recommend_user_message,
)
from app.config import settings

logger = logging.getLogger(__name__)


# ════════════════════════════════════════════════════
# AI 推荐加仓档位
# ════════════════════════════════════════════════════

def recommend_add_tiers(
    fund_name: str,
    total_buy_amount: float,
    initial_principal: float,
    max_investment: float,
    current_return_rate: float,
    current_market_value: float,
    hold_days: int = 0,
    macro_analysis: Optional[dict] = None,
    market_context: str = "",
) -> dict:
    """
    AI 根据基金情况 + 宏观政策分析，推荐合理的金字塔加仓档位 + 止盈止损。

    现在通过 _build_recommend_user_message 构建 user_message，
    消除了与流式版之间 budget_info / macro_text / bold_prefix 的重复代码。

    Args:
        macro_analysis: 宏观政策分析结果，由 analyze_fund_macro() 返回
        market_context: 实时市场数据 + 回测结论文本（估值分位、档位回测等）

    Returns:
        {"tiers": [...], "stopProfitLine": float, "stopLossLine": float,
         "stopProfitRatio": float, "stopLossRatio": float,
         "strategyStyle": str, "explanation": str}
    """
    try:
        user_message = _build_recommend_user_message(
            fund_name, total_buy_amount, initial_principal, max_investment,
            current_return_rate, current_market_value, hold_days,
            macro_analysis, market_context,
        )

        messages = [
            {"role": "system", "content": TIER_RECOMMEND_PROMPT},
            {"role": "user", "content": user_message},
        ]

        text = _call_llm_with_retry(messages, temperature=0.3, max_tokens=2000)
        try:
            result = _safe_parse_json(text)
        except json.JSONDecodeError:
            logger.warning("安全 JSON 解析失败，尝试暴力兜底。原始文本前200字: %s...", text[:200])
            result = _brute_parse_json(text)
            if not result.get("tiers"):
                raise RuntimeError("AI 返回格式异常，请重试")
            logger.warning("暴力兜底解析成功，提取到 %d 个档位", len(result["tiers"]))

        if "tiers" in result:
            return {
                "strategyType": result.get("strategyType", "downside"),
                "tiers": result["tiers"],
                "pullbackTiers": result.get("pullbackTiers", []),
                "stopProfitLine": result.get("stopProfitLine", 0),
                "stopLossLine": result.get("stopLossLine", 0),
                "stopProfitRatio": result.get("stopProfitRatio", 0),
                "stopLossRatio": result.get("stopLossRatio", 0),
                "strategyStyle": result.get("strategyStyle", "标准策略"),
                "explanation": result.get("explanation", ""),
            }
        raise ValueError("AI 返回格式不正确，缺少 tiers 字段")

    except RuntimeError:
        raise
    except json.JSONDecodeError as e:
        logger.error("AI 推荐档位 JSON 解析失败: %s, 原始: %s", e, text[:500])
        raise RuntimeError("AI 返回格式异常，请重试")
    except ValueError as e:
        logger.error("AI 推荐档位解析失败（缺少关键字段）: %s, 原始: %s", e, text[:500])
        raise RuntimeError("AI 返回格式异常，请重试")
    except Exception as e:
        logger.error("AI 推荐档位失败: %s", e)
        raise RuntimeError(f"AI 服务暂时不可用: {e}")


def recommend_add_tiers_stream(
    fund_name: str,
    total_buy_amount: float,
    initial_principal: float,
    max_investment: float,
    current_return_rate: float,
    current_market_value: float,
    hold_days: int = 0,
    macro_analysis: Optional[dict] = None,
    market_context: str = "",
):
    """流式版：AI 推荐加仓档位（生成器），同样使用 _build_recommend_user_message。"""
    user_message = _build_recommend_user_message(
        fund_name, total_buy_amount, initial_principal, max_investment,
        current_return_rate, current_market_value, hold_days,
        macro_analysis, market_context,
    )
    messages = [
        {"role": "system", "content": TIER_RECOMMEND_PROMPT},
        {"role": "user", "content": user_message},
    ]
    yield from _call_llm_stream(messages, temperature=0.3, max_tokens=2000)


# ════════════════════════════════════════════════════
# AI 操作评价
# ════════════════════════════════════════════════════

def evaluate_operation(
    fund_name: str,
    action_type: str,
    amount: float,
    return_rate: float,
    note: str = "",
    fund_context: Optional[str] = None,
) -> str:
    """
    AI 评价一次买卖操作

    Args:
        fund_name: 基金名称
        action_type: 操作类型（买入/卖出）
        amount: 操作金额
        return_rate: 操作时的收益率
        note: 操作备注
        fund_context: 基金持仓上下文（可选）

    Returns:
        AI 评价文本
    """
    try:
        client = _get_client()

        user_message = (
            f"请评价以下这次基金操作：\n\n"
            f"基金名称：{fund_name}\n"
            f"操作类型：{action_type}\n"
            f"操作金额：¥{amount:,.2f}\n"
            f"操作时收益率：{return_rate:.2f}%\n"
            f"操作原因/备注：{note or '无备注'}\n"
        )

        if fund_context:
            user_message += f"\n当前持仓概况：\n{fund_context}"

        messages = [
            {"role": "system", "content": EVALUATE_OPERATION_PROMPT},
            {"role": "user", "content": user_message},
        ]

        response = client.chat.completions.create(
            model=settings.fast_model,
            messages=messages,
            temperature=0.5,
        )
        return response.choices[0].message.content.strip()

    except RuntimeError:
        raise
    except Exception as e:
        logger.error("操作评价失败: %s", e)
        raise RuntimeError(f"AI 评价服务暂时不可用: {e}")


def evaluate_operation_stream(
    fund_name: str,
    action_type: str,
    amount: float,
    return_rate: float,
    note: str = "",
    fund_context: Optional[str] = None,
):
    """流式版：AI 评价一次买卖操作（生成器）"""
    user_message = (
        f"请评价以下这次基金操作：\n\n"
        f"基金名称：{fund_name}\n"
        f"操作类型：{action_type}\n"
        f"操作金额：¥{amount:,.2f}\n"
        f"操作时收益率：{return_rate:.2f}%\n"
        f"操作原因/备注：{note or '无备注'}\n"
    )
    if fund_context:
        user_message += f"\n当前持仓概况：\n{fund_context}"

    messages = [
        {"role": "system", "content": EVALUATE_OPERATION_PROMPT},
        {"role": "user", "content": user_message},
    ]
    yield from _call_llm_stream(messages, temperature=0.5, max_tokens=512)


# ════════════════════════════════════════════════════
# AI 整体组合分析
# ════════════════════════════════════════════════════

def analyze_overall_portfolio(portfolio_data: str) -> str:
    """
    AI 对用户全部基金持仓进行整体分析并给出操作建议

    Args:
        portfolio_data: 格式化后的全部基金持仓数据文本

    Returns:
        AI 分析建议文本
    """
    try:
        messages = [
            {"role": "system", "content": OVERALL_ANALYSIS_PROMPT},
            {"role": "user", "content": portfolio_data},
        ]
        result = _call_llm_with_retry(messages, temperature=0.5, max_tokens=2000)
        return result
    except RuntimeError:
        raise
    except Exception as e:
        logger.error("整体组合分析失败: %s", e)
        raise RuntimeError(f"AI 服务暂时不可用: {e}")


def analyze_overall_portfolio_stream(portfolio_data: str):
    """流式版：AI 对全部基金持仓进行整体分析，逐块返回内容（生成器）"""
    logger.info("开始流式整体组合分析，输入长度: %d", len(portfolio_data))
    messages = [
        {"role": "system", "content": OVERALL_ANALYSIS_PROMPT},
        {"role": "user", "content": portfolio_data},
    ]
    yield from _call_llm_stream(messages, temperature=0.5, max_tokens=2000)
    logger.info("流式整体组合分析完成")
