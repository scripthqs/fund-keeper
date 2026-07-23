"""
AI 投资顾问对话 & 策略解释。
"""

import logging
from typing import Dict, List, Optional

from ._common import (
    _get_client,
    _call_llm_stream,
    INVESTMENT_ADVISOR_PROMPT,
    INTERPRET_ADVICE_PROMPT,
    _build_interpret_user_message,
)
from app.config import settings

logger = logging.getLogger(__name__)


def chat_with_advisor(
    user_message: str,
    fund_context: Optional[str] = None,
    history: Optional[List[Dict]] = None,
) -> str:
    """
    与投资顾问 Agent 对话

    Args:
        user_message: 用户消息
        fund_context: 基金持仓上下文（由前端构建）
        history: 历史对话记录 [{role, content}, ...]

    Returns:
        AI 回复文本
    """
    try:
        client = _get_client()

        system_content = INVESTMENT_ADVISOR_PROMPT
        if fund_context:
            system_content += f"\n\n{fund_context}"

        messages = [{"role": "system", "content": system_content}]
        if history:
            for msg in history[-20:]:
                messages.append({"role": msg["role"], "content": msg["content"]})
        messages.append({"role": "user", "content": user_message})

        response = client.chat.completions.create(
            model=settings.LLM_MODEL,
            messages=messages,
        )
        return response.choices[0].message.content

    except RuntimeError:
        raise
    except Exception as e:
        logger.error("投资顾问对话失败: %s", e)
        raise RuntimeError(f"AI 服务暂时不可用: {e}")


def chat_with_advisor_stream(
    user_message: str,
    fund_context: Optional[str] = None,
    history: Optional[List[Dict]] = None,
):
    """流式版：与投资顾问 Agent 对话，逐块返回内容（生成器）"""
    system_content = INVESTMENT_ADVISOR_PROMPT
    if fund_context:
        system_content += f"\n\n{fund_context}"

    messages = [{"role": "system", "content": system_content}]
    if history:
        for msg in history[-20:]:
            messages.append({"role": msg["role"], "content": msg["content"]})
    messages.append({"role": "user", "content": user_message})

    yield from _call_llm_stream(messages, temperature=0.3, max_tokens=2048, model=settings.LLM_MODEL)


def interpret_advice(
    fund_name: str,
    fund_data: dict,
    rule_result: dict,
    warning: Optional[dict] = None,
    config_info: Optional[dict] = None,
) -> str:
    """
    用自然语言解读规则引擎的分析结果。
    
    现在通过 _build_interpret_user_message 构建 user_message，
    消除了与流式版之间 warn_text / config_text 的重复代码。

    Args:
        fund_name: 基金名称
        fund_data: 基金基础数据 {marketValue, todayChange, totalReturn, holdDays}
        rule_result: 规则引擎输出 {type, title, message, actionType, actionAmount}
        warning: 预警信息 {level, safetyCushion, breakEvenDrop, recoveryNeeded}
        config_info: 投资配置 {stopProfitLine, stopLossLine, addPositionLine, trailingStop}

    Returns:
        AI 解读文本
    """
    try:
        client = _get_client()

        user_message = _build_interpret_user_message(
            fund_name, fund_data, rule_result, warning, config_info
        )

        messages = [
            {"role": "system", "content": INTERPRET_ADVICE_PROMPT},
            {"role": "user", "content": user_message},
        ]

        response = client.chat.completions.create(
            model=settings.fast_model,
            messages=messages,
        )
        return response.choices[0].message.content.strip()

    except RuntimeError:
        raise
    except Exception as e:
        logger.error("操作建议解读失败: %s", e)
        raise RuntimeError(f"AI 服务暂时不可用: {e}")


def interpret_advice_stream(
    fund_name: str,
    fund_data: dict,
    rule_result: dict,
    warning: Optional[dict] = None,
    config_info: Optional[dict] = None,
):
    """流式版：用自然语言解读规则引擎的分析结果（生成器）。同样使用 _build_interpret_user_message。"""
    user_message = _build_interpret_user_message(
        fund_name, fund_data, rule_result, warning, config_info
    )
    messages = [
        {"role": "system", "content": INTERPRET_ADVICE_PROMPT},
        {"role": "user", "content": user_message},
    ]
    yield from _call_llm_stream(messages, temperature=0.3, max_tokens=512)
