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


# ==================== 每日数据智能解析 ====================

DAILY_PARSE_PROMPT = """你是一个数据解析助手。用户会用自然语言描述今日基金的涨跌情况。
你需要从用户消息中提取出对应的基金和涨跌幅数据。

**重要规则：**
1. 只解析"用户基金列表"中明确存在的基金（通过名称模糊匹配）
2. 如果用户提到某个基金名称但未给出涨跌幅，则不对该基金输出
3. 如果用户说"全部""所有"等泛指，则为列表中的每只基金都输出
4. todayChange 是涨跌幅百分比，正数表示上涨，负数表示下跌
5. 只返回纯 JSON 数组，不要包含任何 markdown 标记或额外文字"""


def parse_daily_data(
    user_message: str,
    funds: List[dict],
) -> List[dict]:
    """
    智能解析用户每日收益的自然语言描述

    Args:
        user_message: 用户自然语言消息，如 "今天白酒涨了2%，医疗跌了1.5%"
        funds: 基金列表 [{"id": "xxx", "name": "白酒", "currentReturnRate": 10.5}, ...]

    Returns:
        [{"fundId": "xxx", "fundName": "白酒", "todayChange": 2.0}, ...]
    """
    try:
        client = _get_client()

        # 构建基金列表文本
        fund_lines = []
        for f in funds:
            fund_lines.append(
                f"- ID: {f['id']}, 名称: {f['name']}, 当前收益率: {f.get('currentReturnRate', 0):.2f}%"
            )
        fund_list_text = "\n".join(fund_lines)

        system_content = DAILY_PARSE_PROMPT
        user_content = (
            f"用户基金列表：\n{fund_list_text}\n\n"
            f"用户消息：{user_message}\n\n"
            f'请返回 JSON 数组，格式：[{{"fundId":"基金ID","fundName":"基金名称","todayChange":涨跌幅百分比}}]'
        )

        messages = [
            {"role": "system", "content": system_content},
            {"role": "user", "content": user_content},
        ]

        response = client.chat.completions.create(
            model=settings.LLM_MODEL,
            messages=messages,
        )
        text = response.choices[0].message.content.strip()

        # 提取 JSON 数组
        # 处理 AI 可能返回 ```json ... ``` 包裹的情况
        if "```" in text:
            # 提取代码块内容
            start = text.find("[")
            end = text.rfind("]")
            if start != -1 and end != -1:
                text = text[start:end + 1]

        parsed = json.loads(text)
        if not isinstance(parsed, list):
            logger.warning("AI 返回的不是数组: %s", text)
            return []

        # 为每个结果补齐 fundName（通过 fundId 从 funds 列表中查找）
        fund_map = {f["id"]: f.get("currentReturnRate", 0) for f in funds}
        for item in parsed:
            fid = item.get("fundId", "")
            if fid in fund_map:
                item["totalReturn"] = round(fund_map[fid], 2)
            else:
                item["totalReturn"] = 0

        return parsed

    except RuntimeError:
        raise
    except json.JSONDecodeError as e:
        logger.error("解析 AI 返回的 JSON 失败: %s, 原文: %s", e, text if "text" in dir() else "N/A")
        return []
    except Exception as e:
        logger.error("每日数据解析失败: %s", e)
        raise RuntimeError(f"AI 解析服务异常: {e}")
