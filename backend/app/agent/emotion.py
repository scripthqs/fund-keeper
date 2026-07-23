"""
毒舌情绪文案生成。
"""

import json
import logging

from ._common import _get_client, _call_llm_stream, EMOTION_SYSTEM_PROMPT
from app.config import settings

logger = logging.getLogger(__name__)


def generate_emotion(
    fund_name: str,
    today_change: float,
    total_return: float,
    market_value: float,
) -> dict:
    """
    生成情绪文案（毒舌/搞笑投资段子）

    Returns:
        {"title": str, "lines": List[str]}
    """
    try:
        client = _get_client()

        is_suspicious = total_return >= 50
        system_content = EMOTION_SYSTEM_PROMPT
        if is_suspicious:
            system_content += "用户收益率超50%，必须先在 title 里质疑是不是吹牛逼！"

        user_content = (
            f"基金：{fund_name}，今日涨跌：{today_change:.2f}%，"
            f"总收益率：{total_return:.2f}%，"
            f"市值¥{market_value:,.2f}"
        )

        messages = [
            {"role": "system", "content": system_content},
            {"role": "user", "content": user_content},
        ]

        response = client.chat.completions.create(
            model=settings.fast_model,
            messages=messages,
        )
        text = response.choices[0].message.content
        text = text.strip()

        try:
            parsed = json.loads(text)
            if "title" in parsed and "lines" in parsed:
                return parsed
        except json.JSONDecodeError:
            pass

        lines = [l.strip() for l in text.split("\n") if l.strip()]
        return {
            "title": lines[0][:15] if lines else "AI 情绪加油站",
            "lines": lines if lines else ["AI 暂时不在线，但你的心情我懂"],
        }

    except RuntimeError:
        raise
    except Exception as e:
        logger.error("情绪文案生成失败: %s", e)
        return {
            "title": "😅 AI 暂时不在线",
            "lines": ["AI 情绪生成服务暂时不可用，稍后再试"],
        }


def generate_emotion_stream(
    fund_name: str,
    today_change: float,
    total_return: float,
    market_value: float,
):
    """流式版：生成情绪文案，逐块返回内容（生成器）"""
    is_suspicious = total_return >= 50
    system_content = EMOTION_SYSTEM_PROMPT
    if is_suspicious:
        system_content += "用户收益率超50%，必须先在 title 里质疑是不是吹牛逼！"

    user_content = (
        f"基金：{fund_name}，今日涨跌：{today_change:.2f}%，"
        f"总收益率：{total_return:.2f}%，"
        f"市值¥{market_value:,.2f}"
    )

    messages = [
        {"role": "system", "content": system_content},
        {"role": "user", "content": user_content},
    ]
    yield from _call_llm_stream(messages, temperature=0.5, max_tokens=512)
