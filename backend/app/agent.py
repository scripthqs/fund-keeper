"""AI Agent 层 - 投资顾问 Agent 与情绪文案生成"""

import json
import logging
import re
from datetime import datetime
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


# ==================== AI 宏观分析 ====================

MACRO_ANALYSIS_PROMPT = """你是一位宏观经济与政策研究专家。请根据基金名称分析该基金所处的行业/赛道，结合当前（{current_date}）中国最新的国家政策方向和发展趋势，评估该基金受政策利好的程度。注意：政策变化频繁，必须以当前时间节点最新的政策为准，不要使用过时的信息。

请严格按以下 JSON 格式输出，不要包含 markdown 代码块标记，只输出纯 JSON：

{"sector":"所属行业/赛道","policyScore":75,"keyPolicies":["政策1","政策2"],"trend":"趋势判断","aggressiveness":0.2,"analysis":"简要分析"}

字段说明：
- sector: 该基金对应的行业/赛道（如"半导体""新能源""消费""医疗""军工""AI科技""白酒""债市"等）
- policyScore: 政策支持力度评分（0-100），越高越受政策支持
  - 80-100: 国家重点战略方向（如芯片自主、新能源、AI、高端制造、军工、数字经济）
  - 60-79: 有政策支撑但非核心（如消费升级、医疗健康、新基建）
  - 40-59: 中性行业，无明显政策倾斜
  - 20-39: 政策收紧或监管趋严的行业
  - 0-19: 政策明确打压或限制的行业
- keyPolicies: 关联的国家政策或战略（2-4条，如"十四五数字经济规划""新质生产力""国产替代""双碳目标"等）
- trend: 一句话总结未来1-2年该赛道的政策趋势
- aggressiveness: 策略调整系数（-0.5 ~ +0.5），正值表示可以更激进，负值表示应该更保守
  - +0.3~+0.5: 政策大力支持，可大幅提高风险偏好
  - +0.1~+0.3: 政策偏暖，可适当积极
  - -0.1~+0.1: 中性，维持标准策略
  - -0.3~-0.1: 政策不明朗，建议保守
  - -0.5~-0.3: 政策风险较大，强烈建议保守
- analysis: 50字以内简要分析"""


def analyze_fund_macro(fund_name: str) -> dict:
    """
    AI 分析基金的宏观政策环境，评估国家政策利好程度

    Returns:
        {"sector": str, "policyScore": int, "keyPolicies": list,
         "trend": str, "aggressiveness": float, "analysis": str}
    """
    try:
        client = _get_client()
        current_date = datetime.now().strftime("%Y年%m月%d日 %H:%M:%S")

        # 动态注入当前精确时间到系统提示词
        system_prompt = MACRO_ANALYSIS_PROMPT.replace("{current_date}", current_date)

        user_message = (
            f"请分析以下基金所处的行业赛道，评估当前（{current_date}）中国国家政策对其的支持力度：\n\n"
            f"基金名称：{fund_name}\n\n"
            f"请结合中国最新的国家战略（如新质生产力、国产替代、双碳目标、数字经济、"
            f"扩大内需、科技自立自强等），判断该基金所在赛道是否属于国家重点支持方向。"
            f"请确保分析基于最近一个月内的最新政策动向，反映当前时间节点的真实情况。"
        )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ]

        response = client.chat.completions.create(
            model=settings.LLM_MODEL,
            messages=messages,
            temperature=0.3,
        )
        text = response.choices[0].message.content.strip()
        raw_text = text  # 保留原始内容用于错误日志

        # 1. 处理 markdown 代码块
        if "```" in text:
            match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
            if match:
                text = match.group(1).strip()

        # 2. 提取第一个完整 JSON 对象（处理 AI 在 JSON 前后加说明文字）
        if not text.startswith("{"):
            match = re.search(r"\{.*\}", text, re.DOTALL)
            if match:
                text = match.group(0).strip()

        # 3. 清理常见格式问题：尾逗号（JSON 标准不允许）
        text = re.sub(r",\s*(\}|\])", r"\1", text)

        result = json.loads(text)
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
        # 返回错误信息给前端，不阻塞流程
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
        # 返回错误信息给前端，不阻塞流程
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


# ==================== AI 推荐加仓档位 ====================

TIER_RECOMMEND_PROMPT = """你是一位资深基金投资策略师，擅长设计金字塔加仓方案和止盈止损策略。用户需要为一只基金配置完整的交易策略。

请严格按以下 JSON 格式输出，不要包含 markdown 代码块标记，只输出纯 JSON：

{"tiers":[{"line":-8,"ratio":5},{"line":-13,"ratio":10},{"line":-19,"ratio":18},{"line":-26,"ratio":30}],"stopProfitLine":25,"stopLossLine":-30,"stopProfitRatio":20,"stopLossRatio":60,"strategyStyle":"标准策略","explanation":"你的解释"}

加仓设计原则：
1. line（触发阈值，负数）：从浅到深均匀分布，第1档约-6~-10%，每档间隔约4~8%。最后一档不要超过 -35%
2. ratio（买入比例，正数）：初始本金的百分比。越往后越大（金字塔加仓），比例递增明显
3. 所有比例加起来的总金额不能超过「剩余预算」。但也要合理利用预算空间，不能太保守
4. 如果剩余预算很充裕（是初始本金的3倍以上），可以设得积极一些

止盈止损设计原则：
5. stopProfitLine（止盈触发线，正数，%）：根据基金类型和当前市况。偏股型基金建议 15-35%，债基 5-10%。持有天数短（<30天）宜设低
6. stopLossLine（止损触发线，负数，%）：根据用户最大可承受亏损。偏股型通常 -20~-35%，保守型 -15~-20%。不要设得太深，否则止损就失去意义了
7. stopProfitRatio（止盈卖出比例，正数，%）：建议在 15-30% 之间，分批止盈降低踏空风险
8. stopLossRatio（止损卖出比例，正数，%）：建议在 50-80% 之间，尽量多割以保护本金

🔴 策略激进程度调整（非常重要）：
我会在用户消息中提供该基金的「宏观政策分析」，包含 policyScore（政策支持度评分）、aggressiveness（策略调整系数）和 keyPolicies（国家政策）。
- 如果政策大力支持（policyScore >= 80，aggressiveness > 0.2）：加仓档位可以设得更密集（间隔缩小到 3-5%），比例可以更大胆（最高档可达 35-40%），止盈线可以设得更高（25-40%），止损线可以设得更深（-25~-35%）——因为国家背书降低了长期风险
- 如果政策中性（policyScore 40-79，aggressiveness -0.1~0.2）：保持标准策略，按上述 1-8 条原则正常推荐
- 如果政策风险较大（policyScore < 40，aggressiveness < -0.1）：加仓档位设得更稀疏（间隔加大到 6-10%），比例更保守（最高档不超过 20%），止盈线设得更低（10-20%），止损线设得更浅（-10~-20%）——因为政策不确定性增加了风险

9. strategyStyle: 用简短标签说明策略风格，如"激进型""标准型""保守型""防御型"
10. explanation 用 100 字以内中文解释推荐思路，要覆盖：宏观政策判断 + 加仓逻辑 + 止盈止损逻辑"""


def recommend_add_tiers(
    fund_name: str,
    total_buy_amount: float,
    initial_principal: float,
    max_investment: float,
    current_return_rate: float,
    current_market_value: float,
    hold_days: int = 0,
    macro_analysis: Optional[dict] = None,
) -> dict:
    """
    AI 根据基金情况 + 宏观政策分析，推荐合理的金字塔加仓档位 + 止盈止损

    Args:
        macro_analysis: 宏观政策分析结果，由 analyze_fund_macro() 返回

    Returns:
        {"tiers": [...], "stopProfitLine": float, "stopLossLine": float,
         "stopProfitRatio": float, "stopLossRatio": float,
         "strategyStyle": str, "explanation": str}
    """
    try:
        client = _get_client()

        remaining = max_investment - total_buy_amount if max_investment > 0 else float("inf")
        remaining_str = f"¥{remaining:,.0f}" if remaining < float("inf") else "无上限（未设置最大投入）"

        # 构建宏观分析部分
        macro_text = ""
        if macro_analysis and macro_analysis.get("sector") != "未知":
            policies = "、".join(macro_analysis.get("keyPolicies", [])) or "暂无明确关联政策"
            macro_text = (
                f"\n\n【宏观政策分析】\n"
                f"所属行业/赛道：{macro_analysis.get('sector', '未知')}\n"
                f"政策支持评分：{macro_analysis.get('policyScore', 50)}/100\n"
                f"关联国家政策：{policies}\n"
                f"政策趋势：{macro_analysis.get('trend', '')}\n"
                f"策略调整建议：{'应更激进' if macro_analysis.get('aggressiveness', 0) > 0.15 else '应更保守' if macro_analysis.get('aggressiveness', 0) < -0.15 else '维持标准'}"
                f"（调整系数 {macro_analysis.get('aggressiveness', 0):+.1f}）\n"
                f"分析摘要：{macro_analysis.get('analysis', '')}\n"
            )

        user_message = (
            f"请为以下基金推荐 4 档金字塔加仓方案和止盈止损线：\n\n"
            f"基金名称：{fund_name}\n"
            f"初始本金：¥{initial_principal:,.2f}\n"
            f"已投入金额：¥{total_buy_amount:,.2f}\n"
            f"投入上限：{'¥{:,.2f}'.format(max_investment) if max_investment > 0 else '未设置'}\n"
            f"剩余可投入预算：{remaining_str}\n"
            f"当前收益率：{current_return_rate:.2f}%\n"
            f"当前市值：¥{current_market_value:,.2f}\n"
            f"已持有天数：{hold_days}天"
            f"{macro_text}"
        )

        messages = [
            {"role": "system", "content": TIER_RECOMMEND_PROMPT},
            {"role": "user", "content": user_message},
        ]

        response = client.chat.completions.create(
            model=settings.LLM_MODEL,
            messages=messages,
            temperature=0.3,
        )
        text = response.choices[0].message.content.strip()

        # 尝试解析 JSON，处理 markdown 代码块
        if "```" in text:
            # 提取代码块内容
            match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
            if match:
                text = match.group(1).strip()

        # 尝试提取第一个完整 JSON 对象（处理 AI 可能在 JSON 前后加说明文字的情况）
        if not text.startswith("{"):
            json_match = re.search(r"\{.*\}", text, re.DOTALL)
            if json_match:
                text = json_match.group(0).strip()

        # 清理常见格式问题：尾逗号
        text = re.sub(r",\s*(\}|\])", r"\1", text)

        result = json.loads(text)
        if "tiers" in result:
            return {
                "tiers": result["tiers"],
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
        logger.error("AI 推荐档位 JSON 解析失败: %s, 原始: %s", e, text)
        raise RuntimeError(f"AI 返回格式异常，请重试")
    except Exception as e:
        logger.error("AI 推荐档位失败: %s", e)
        raise RuntimeError(f"AI 服务暂时不可用: {e}")




