"""AI Agent 层 - 投资顾问 Agent 与情绪文案生成"""

import json
import logging
from typing import Dict, List, Optional

from openai import OpenAI

from app.config import settings

logger = logging.getLogger(__name__)

# ==================== LLM 初始化 ====================

_client = None


def _get_client():
    """懒加载 OpenAI 客户端实例"""
    global _client
    if _client is not None:
        return _client

    if not settings.llm_configured:
        raise RuntimeError(
            "LLM API Key 未配置，请在 .env 文件中设置 LLM_API_KEY"
        )

    _client = OpenAI(
        api_key=settings.LLM_API_KEY,
        base_url=settings.LLM_BASE_URL,
    )
    logger.info("OpenAI 客户端初始化完成: model=%s", settings.LLM_MODEL)
    return _client




# ==================== 系统提示词 ====================

INVESTMENT_ADVISOR_PROMPT = """你是一位专业的基金投资顾问。你掌握用户实时的基金持仓数据。请根据数据给出客观、理性的分析建议，不预测具体涨跌，只做风险评估和策略建议。回答简洁有条理，使用中文。"""

EMOTION_SYSTEM_PROMPT = """你是一个理财陪伴"嘴替"。用 JSON 格式回复，格式：{"title":"不超过15字的标题","lines":["段子1","段子2","段子3"]}。风格必须：毒舌、夸张、接地气、说人话。标题和段子都要带强烈情绪。"""

INTERPRET_ADVICE_PROMPT = """你是一位亲切、务实的基金投资顾问。系统基于预设规则分析了用户持仓并给出操作建议。你需要用通俗的人话解读这个结果。

解读要求：
1. 先用一句话总结判断结论，点出核心逻辑，不要说"引擎""系统""规则"等词，直接像朋友在分析
2. 结合具体的收益率、安全垫、回本难度等数据，解释为什么得出这个建议
3. 给出 1-2 条务实的操作提醒（比如"明天如果继续跌到X%就触发加仓了"）
4. 语气轻松自然，像朋友聊天，200字以内，不用 emoji，不卖关子，避免使用"引擎说""规则说""系统说""引擎判断""规则判断""系统判断""引擎建议""规则建议""系统建议""引擎认为""规则认为""系统认为""引擎给出""规则给出""系统给出""引擎觉得""规则觉得""系统觉得""引擎提示""规则提示""系统提示""引擎警告""规则警告""系统警告"等说法"""



# ==================== 对外接口 ====================

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

        # 构建系统提示（包含基金上下文）
        system_content = INVESTMENT_ADVISOR_PROMPT
        if fund_context:
            system_content += f"\n\n{fund_context}"

        # 构建消息列表
        messages = [{"role": "system", "content": system_content}]
        if history:
            # 只保留最近 20 条历史
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
            model=settings.LLM_MODEL,
            messages=messages,
        )
        text = response.choices[0].message.content
        text = text.strip()

        # 尝试解析 JSON
        try:
            parsed = json.loads(text)
            if "title" in parsed and "lines" in parsed:
                return parsed
        except json.JSONDecodeError:
            pass

        # 如果 AI 没返回标准 JSON，按纯文本处理
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


def interpret_advice(
    fund_name: str,
    fund_data: dict,
    rule_result: dict,
    warning: Optional[dict] = None,
    config_info: Optional[dict] = None,
) -> str:
    """
    用自然语言解读规则引擎的分析结果

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

        # 拼接规则结果
        result_text = (
            f"规则类型：{rule_result.get('type', '未知')}\n"
            f"结论标题：{rule_result.get('title', '')}\n"
            f"详细说明：{rule_result.get('message', '')}\n"
        )
        if rule_result.get('actionAmount') is not None:
            result_text += f"建议操作：{rule_result.get('actionType', '操作')} ¥{rule_result['actionAmount']:,.0f}\n"

        # 拼接基金数据
        fund_text = (
            f"基金名称：{fund_name}\n"
            f"当前市值：¥{fund_data.get('marketValue', 0):,.2f}\n"
            f"今日涨跌幅：{fund_data.get('todayChange', 0):.2f}%\n"
            f"总收益率：{fund_data.get('totalReturn', 0):.2f}%\n"
            f"持有天数：{fund_data.get('holdDays', 0)} 天\n"
        )

        # 拼接预警
        warn_text = ""
        if warning:
            parts = []
            if warning.get('safetyCushion') is not None:
                parts.append(f"安全垫（可抵御跌幅）：{warning['safetyCushion']:.2f}%")
            if warning.get('breakEvenDrop') is not None:
                parts.append(f"盈亏归零所需跌幅：{warning['breakEvenDrop']:.2f}%")
            if warning.get('recoveryNeeded') is not None:
                parts.append(f"回本所需涨幅：{warning['recoveryNeeded']:.1f}%")
            if parts:
                warn_text = "\n".join(parts) + "\n"

        # 拼接配置
        config_text = ""
        if config_info:
            items = []
            if config_info.get('stopProfitLine') is not None:
                items.append(f"止盈线 ≥{config_info['stopProfitLine']}%")
            if config_info.get('stopLossLine') is not None:
                items.append(f"止损线 ≤{config_info['stopLossLine']}%")
            if config_info.get('addPositionLine') is not None:
                items.append(f"加仓线 ≤{config_info['addPositionLine']}%")
            if items:
                config_text = "投资规则：" + "，".join(items) + "\n"

        warn_display = warn_text or "无特殊预警"
        user_message = (
            f"以下是一只基金的规则引擎分析结果，请帮我解读：\n\n"
            f"{fund_text}\n"
            f"{config_text}\n"
            f"【规则分析结果】\n{result_text}\n"
            f"【预警数据】\n{warn_display}\n"
            f"请用200字以内解读这个结果。"
        )

        messages = [
            {"role": "system", "content": INTERPRET_ADVICE_PROMPT},
            {"role": "user", "content": user_message},
        ]

        response = client.chat.completions.create(
            model=settings.LLM_MODEL,
            messages=messages,
        )
        return response.choices[0].message.content.strip()

    except RuntimeError:
        raise
    except Exception as e:
        logger.error("操作建议解读失败: %s", e)
        raise RuntimeError(f"AI 服务暂时不可用: {e}")




