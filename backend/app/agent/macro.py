"""
AI 宏观政策分析。
"""

import json
import logging
from datetime import datetime

from ._common import (
    _call_llm_with_retry,
    _call_llm_stream,
    _safe_parse_json,
    MACRO_ANALYSIS_PROMPT,
    MACRO_ANALYSIS_STREAM_PROMPT,
)

logger = logging.getLogger(__name__)


def analyze_fund_macro(fund_name: str, realtime_context: str = "") -> dict:
    """
    AI 分析基金的宏观政策环境，评估国家政策利好程度

    Args:
        fund_name: 基金名称
        realtime_context: 实时市场数据文本（由 format_realtime_context 生成），
            注入后可弥补 LLM 知识截止日期，让分析基于真实行情

    Returns:
        {"sector": str, "policyScore": int, "keyPolicies": list,
         "trend": str, "aggressiveness": float, "analysis": str}
    """
    try:
        current_date = datetime.now().strftime("%Y年%m月%d日 %H:%M:%S")
        system_prompt = MACRO_ANALYSIS_PROMPT.replace("{current_date}", current_date)

        data_block = ""
        if realtime_context:
            data_block = (
                f"\n\n以下为实时市场数据（行情接口于 {current_date} 获取，是你知识截止日期之后的真实数据）：\n"
                f"{realtime_context}\n"
                f"请优先基于以上数据判断该基金当前所处的市场位置、趋势强弱与波动风险；"
                f"政策面如无法确认最新动向，请明确标注为推断。"
            )

        user_message = (
            f"请分析以下基金所处的行业赛道，评估当前（{current_date}）中国国家政策对其的支持力度：\n\n"
            f"基金名称：{fund_name}\n\n"
            f"请结合中国最新的国家战略（如新质生产力、国产替代、双碳目标、数字经济、"
            f"扩大内需、科技自立自强等），判断该基金所在赛道是否属于国家重点支持方向。"
            f"请确保分析基于最近一个月内的最新政策动向，反映当前时间节点的真实情况。"
            f"{data_block}"
        )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ]

        text = _call_llm_with_retry(messages, temperature=0.3)
        raw_text = text
        result = _safe_parse_json(text)
        return {
            "sector": result.get("sector", "未知"),
            "policyScore": result.get("policyScore", 50),
            "keyPolicies": result.get("keyPolicies", []),
            "trend": result.get("trend", ""),
            "aggressiveness": result.get("aggressiveness", 0),
            "analysis": result.get("analysis", ""),
        }

    except RuntimeError:
        raise
    except json.JSONDecodeError as e:
        logger.error("宏观分析 JSON 解析失败: %s", e)
        logger.error("原始返回内容(前500字符): %s", str(raw_text)[:500] if 'raw_text' in dir() else str(text)[:500])
        return {
            "error": True,
            "message": f"AI 返回格式无法解析：{e}",
            "sector": "未知",
            "policyScore": 50,
            "keyPolicies": [],
            "trend": "未能完成分析",
            "aggressiveness": 0,
            "analysis": "宏观分析未启用，当前档位推荐基于基金本身数据生成，未参考宏观政策。",
        }
    except Exception as e:
        import traceback
        logger.error("宏观分析失败: %s", e)
        logger.error("详细堆栈: %s", traceback.format_exc())
        return {
            "error": True,
            "message": f"AI 服务调用失败：{e}",
            "sector": "未知",
            "policyScore": 50,
            "keyPolicies": [],
            "trend": "未能完成分析",
            "aggressiveness": 0,
            "analysis": "宏观分析未启用，当前档位推荐基于基金本身数据生成，未参考宏观政策。",
        }


def analyze_fund_macro_stream(fund_name: str, realtime_context: str = ""):
    """
    流式版：AI 分析基金宏观政策环境，逐块返回内容（生成器）
    文本分析在前，JSON 数据在后。调用方可按 brace 计数分离分析文本和 JSON。

    Args:
        fund_name: 基金名称
        realtime_context: 实时市场数据文本（由 format_realtime_context 生成）

    Yields:
        str: LLM 输出的内容块（包含分析文本和 JSON）
    """
    current_date = datetime.now().strftime("%Y年%m月%d日 %H:%M:%S")
    system_prompt = MACRO_ANALYSIS_STREAM_PROMPT.replace("{current_date}", current_date)

    data_block = ""
    if realtime_context:
        data_block = (
            f"\n\n以下为实时市场数据（行情接口于 {current_date} 获取，是你知识截止日期之后的真实数据）：\n"
            f"{realtime_context}\n"
            f"请优先基于以上数据判断该基金当前所处的市场位置、趋势强弱与波动风险，"
            f"并在中文分析中引用关键数字；政策面如无法确认最新动向，请明确标注为推断。"
        )

    user_message = (
        f"请分析以下基金所处的行业赛道，评估当前（{current_date}）中国国家政策对其的支持力度：\n\n"
        f"基金名称：{fund_name}\n\n"
        f"请结合中国最新的国家战略（如新质生产力、国产替代、双碳目标、数字经济、"
        f"扩大内需、科技自立自强等），判断该基金所在赛道是否属于国家重点支持方向。"
        f"{data_block}"
    )

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message},
    ]
    yield from _call_llm_stream(messages, temperature=0.3, max_tokens=1400)
