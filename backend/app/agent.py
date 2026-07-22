"""AI Agent 层 - 投资顾问 Agent 与情绪文案生成"""

import json
import logging
import re
import time
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
        timeout=180.0,  # 3 分钟超时，流式长文本生成需要足够时间
        max_retries=1,  # 由我们自己的重试逻辑接管
    )
    logger.info("OpenAI 客户端初始化完成: model=%s", settings.LLM_MODEL)
    return _client


def _call_llm_with_retry(messages, temperature=0.3, max_retries=2, max_tokens=1500, model: str = ""):
    """带重试的 LLM 调用，处理临时性 API 故障。默认使用快速模型（LLM_FAST_MODEL，未配置则回退 LLM_MODEL）"""
    client = _get_client()
    last_error = None
    for attempt in range(max_retries + 1):
        try:
            response = client.chat.completions.create(
                model=model or settings.fast_model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            last_error = e
            if attempt < max_retries:
                wait = (attempt + 1) * 0.5  # 递增等待：0.5s, 1s
                logger.warning("LLM 调用失败(第%d/%d次)，%s 后重试: %s", attempt + 1, max_retries + 1, wait, e)
                time.sleep(wait)
    raise RuntimeError(f"LLM 调用 {max_retries + 1} 次均失败: {last_error}")


# ==================== 流式 LLM 调用 ====================

def _call_llm_stream(messages, temperature=0.3, max_tokens=2048, model: str = ""):
    """流式调用 LLM，逐块返回内容（生成器）。默认使用快速模型（LLM_FAST_MODEL，未配置则回退 LLM_MODEL）"""
    client = _get_client()
    use_model = model or settings.fast_model
    for attempt in range(3):
        try:
            logger.info("流式调用 LLM: model=%s, attempt=%d", use_model, attempt + 1)
            response = client.chat.completions.create(
                model=use_model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                stream=True,
            )
            first_chunk_received = False
            reasoning_phase = True  # 推理模型的思考阶段
            for chunk in response:
                if not first_chunk_received:
                    logger.info("收到首个 LLM chunk")
                    first_chunk_received = True
                delta = chunk.choices[0].delta if chunk.choices else None
                if not delta:
                    continue
                # 推理模型的思考过程：跳过内容，只通知前端"思考中"
                if getattr(delta, 'reasoning_content', None):
                    if reasoning_phase:
                        yield '__REASONING__'  # 哨兵：思考开始
                        reasoning_phase = False
                    continue  # 不输出思考内容
                # 正式回答内容
                if delta.content:
                    yield delta.content
            return  # 成功完成
        except Exception as e:
            logger.warning("流式 LLM 调用失败(第%d次): %s", attempt + 1, e)
            if attempt < 2:
                time.sleep((attempt + 1) * 0.5)
    raise RuntimeError("流式 LLM 调用 3 次均失败")


def _safe_parse_json(text: str) -> dict:
    """安全解析 AI 返回的 JSON，处理常见格式问题。

    解析失败会抛出 JSONDecodeError，调用方应使用 _brute_parse_json 兜底。
    """
    if not text or not text.strip():
        raise json.JSONDecodeError("JSON 为空", text or "", 0)

    text = text.strip()

    # 1. 去除 UTF-8 BOM
    if text.startswith("\ufeff"):
        text = text[1:]

    # 2. 提取 markdown 代码块
    if "```" in text:
        match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
        if match:
            text = match.group(1).strip()

    # 3. 如果内容被包裹在 ::JSON:: 之类的分隔符后仍带前后缀，先找第一个 { 到最后一个 }
    brace_start = text.find("{")
    if brace_start > 0:
        brace_end = text.rfind("}")
        if brace_end > brace_start:
            text = text[brace_start:brace_end + 1]

    # 4. 用括号计数精确提取第一个完整 JSON 对象（处理字符串内的 { }）
    if brace_start >= 0 and not text.lstrip().startswith("{"):
        depth = 0
        in_string = False
        escaped = False
        json_end = -1
        for i in range(brace_start, len(text)):
            ch = text[i]
            if escaped:
                escaped = False
                continue
            if ch == "\\":
                escaped = True
                continue
            if ch == '"':
                in_string = not in_string
                continue
            if in_string:
                continue
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    json_end = i + 1
                    break
        if json_end > brace_start:
            text = text[brace_start:json_end].strip()

    # 5. 基本清理
    text = re.sub(r",\s*(\}|\])", r"\1", text)             # 尾逗号
    text = re.sub(r"//[^\n]*", "", text)                    # 行注释
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)  # 块注释
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", text)  # 控制字符

    # 6. 修复单引号、中文引号、Infinity/NaN 等非法字面量
    text = _fix_json_content_quotes(text)
    text = re.sub(r'(?<!["\'])\b(NaN|nan|Infinity|inf|-Infinity|-inf)\b', 'null', text, flags=re.IGNORECASE)

    # 7. 尝试把裸 key 补成双引号（如 {line:-8} → {"line":-8}）
    text = re.sub(r"([{,])\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*:", r'\1"\2":', text)

    def _escape_string_newlines(m):
        content = m.group(1)
        content = content.replace("\n", "\\n").replace("\r", "\\r").replace("\t", "\\t")
        return '"' + content + '"'

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # 8. 强制转义字符串内的控制字符再试
    text = re.sub(r'"((?:[^"\\]|\\.)*)"', _escape_string_newlines, text)

    # 9. 移除多余转义（部分模型会输出 \\" 等）
    text = text.replace('\\"', '"')

    return json.loads(text)


_JSON_FIELD_FALLBACK = re.compile(
    r'"(strategyType|strategyStyle|explanation)"\s*:\s*"([^"]*)"'
    r'|"(stopProfitLine|stopLossLine|stopProfitRatio|stopLossRatio)"\s*:\s*(-?\d+\.?\d*)'
    r'|"(line|ratio)"\s*:\s*(-?\d+\.?\d*)',
    re.DOTALL,
)


def _brute_parse_json(text: str) -> dict:
    """最后的兜底：用正则从任意文本中暴力提取 JSON 字段"""
    result: dict = {"strategyType": "downside", "tiers": [], "pullbackTiers": [],
                    "stopProfitLine": 20, "stopLossLine": -25,
                    "stopProfitRatio": 20, "stopLossRatio": 60,
                    "strategyStyle": "标准策略", "explanation": ""}
    tiers: list = []
    pullback_tiers: list = []
    current_section = None       # "tiers" | "pullbackTiers" | None
    pending_line: Optional[float] = None  # 暂存跨行的 line 值

    # 按行扫描，识别 [tiers] / [pullbackTiers] 区段和其中的 {line, ratio} 对
    for raw_line in text.split("\n"):
        stripped = raw_line.strip()

        # 检测段落标记
        if re.search(r'pullbackTiers|pullback_tiers|回调', stripped, re.IGNORECASE):
            current_section = "pullbackTiers"
            pending_line = None
            continue
        if re.search(r'"tiers"\s*:', stripped) and "pullback" not in stripped.lower():
            current_section = "tiers"
            pending_line = None
            continue

        # 提取当前行的 line 和 ratio（处理单行 JSON "...},{..." 拆成多段）
        for part in re.split(r'(?<=})', stripped):
            line_match = re.search(r'"line"\s*:\s*(-?\d+\.?\d*)', part)
            ratio_match = re.search(r'"ratio"\s*:\s*(-?\d+\.?\d*)', part)

            if line_match and ratio_match:
                # 单行同时有 line 和 ratio
                tier = {"line": float(line_match.group(1)), "ratio": float(ratio_match.group(1))}
                if current_section == "pullbackTiers":
                    pullback_tiers.append(tier)
                else:
                    tiers.append(tier)
                pending_line = None
            elif line_match:
                pending_line = float(line_match.group(1))
            elif ratio_match and pending_line is not None:
                # 跨行匹配到 ratio
                tier = {"line": pending_line, "ratio": float(ratio_match.group(1))}
                if current_section == "pullbackTiers":
                    pullback_tiers.append(tier)
                else:
                    tiers.append(tier)
                pending_line = None

    if tiers:
        result["tiers"] = tiers
    if pullback_tiers:
        result["pullbackTiers"] = pullback_tiers

    # 提取标量字段
    for m in _JSON_FIELD_FALLBACK.finditer(text):
        if m.group(1):  # 字符串字段
            result[m.group(1)] = m.group(2)
        elif m.group(3) and m.group(4):  # 数字字段
            result[m.group(3)] = float(m.group(4))

    return result


def _fix_json_content_quotes(text: str) -> str:
    """修复 AI 在 JSON 字符串值内部误用 ASCII 双引号的问题。
    
    例如 DeepSeek 在 explanation 字段中写：
        "explanation":"选择"上涨回调"策略"
                        ^       ^  这两处 " 破坏了 JSON 结构
    修复为：
        "explanation":"选择\u201c上涨回调\u201d策略"
    """
    # 保护已正确转义的 \"
    placeholder = "\x00ESCAPED_QUOTE\x00"
    text = text.replace('\\"', placeholder)

    # 策略：找到所有 " 的位置，标记哪些是结构性的（作为 JSON 键/值分隔符）
    # 结构性的 " 满足以下条件之一：
    #   1. 前面紧跟 { } , : [ ] 或空白
    #   2. 后面紧跟 { } , : [ ] 或空白
    result = list(text)
    i = 0
    while i < len(result):
        if result[i] != '"':
            i += 1
            continue

        # 判断前面的字符是否为 JSON 结构字符
        prev_char = ''
        j = i - 1
        while j >= 0 and result[j] in ' \t\n\r':
            j -= 1
        if j >= 0:
            prev_char = result[j]

        # 判断后面的字符是否为 JSON 结构字符
        next_char = ''
        j = i + 1
        while j < len(result) and result[j] in ' \t\n\r':
            j += 1
        if j < len(result):
            next_char = result[j]

        is_structural = (
            prev_char in '{[,:' or
            next_char in '}],:' or
            (prev_char == '' and next_char in '}],:') or
            (next_char == '' and prev_char in '{[,:') or
            (prev_char.isdigit() and next_char.isdigit())  # 数字内的引号
        )

        if not is_structural:
            # 可能是内容引号 → 替换为中文引号
            result[i] = '\u201c'  # "
            # 查找配对的右引号
            j2 = i + 1
            while j2 < len(result):
                if result[j2] == '"':
                    # 检查这个引号是否为结构性
                    n_prev = ''
                    k = j2 - 1
                    while k > i and result[k] in ' \t\n\r':
                        k -= 1
                    if k > i:
                        n_prev = result[k]
                    if n_prev not in '{[,:':
                        # 也是内容引号
                        result[j2] = '\u201d'  # "
                        i = j2
                    break
                j2 += 1
        i += 1

    text = ''.join(result)
    # 恢复转义引号
    text = text.replace(placeholder, '\\"')
    return text


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

    # AI 投顾对话是开放式问答，保留推理模型（LLM_MODEL）以获得最佳回答质量
    yield from _call_llm_stream(messages, temperature=0.3, max_tokens=2048, model=settings.LLM_MODEL)


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
            model=settings.fast_model,
            messages=messages,
        )
        return response.choices[0].message.content.strip()

    except RuntimeError:
        raise
    except Exception as e:
        logger.error("操作建议解读失败: %s", e)
        raise RuntimeError(f"AI 服务暂时不可用: {e}")


def _build_interpret_user_message(fund_name, fund_data, rule_result, warning, config_info):
    """构建解读建议的 user message（复用）"""
    result_text = (
        f"规则类型：{rule_result.get('type', '未知')}\n"
        f"结论标题：{rule_result.get('title', '')}\n"
        f"详细说明：{rule_result.get('message', '')}\n"
    )
    if rule_result.get('actionAmount') is not None:
        result_text += f"建议操作：{rule_result.get('actionType', '操作')} ¥{rule_result['actionAmount']:,.0f}\n"

    fund_text = (
        f"基金名称：{fund_name}\n"
        f"当前市值：¥{fund_data.get('marketValue', 0):,.2f}\n"
        f"今日涨跌幅：{fund_data.get('todayChange', 0):.2f}%\n"
        f"总收益率：{fund_data.get('totalReturn', 0):.2f}%\n"
        f"持有天数：{fund_data.get('holdDays', 0)} 天\n"
    )

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
    return (
        f"以下是一只基金的规则引擎分析结果，请帮我解读：\n\n"
        f"{fund_text}\n"
        f"{config_text}\n"
        f"【规则分析结果】\n{result_text}\n"
        f"【预警数据】\n{warn_display}\n"
        f"请用200字以内解读这个结果。"
    )


def interpret_advice_stream(
    fund_name: str,
    fund_data: dict,
    rule_result: dict,
    warning: Optional[dict] = None,
    config_info: Optional[dict] = None,
):
    """流式版：用自然语言解读规则引擎的分析结果（生成器）"""
    user_message = _build_interpret_user_message(fund_name, fund_data, rule_result, warning, config_info)
    messages = [
        {"role": "system", "content": INTERPRET_ADVICE_PROMPT},
        {"role": "user", "content": user_message},
    ]
    yield from _call_llm_stream(messages, temperature=0.3, max_tokens=512)


# ==================== AI 宏观分析 ====================

MACRO_ANALYSIS_PROMPT = """你是宏观经济政策研究员。分析该基金所属行业/赛道，结合当前（{current_date}）中国最新政策评估政策利好程度。注意以当前最新政策为准。输出纯JSON。

{"sector":"行业/赛道","policyScore":75,"keyPolicies":["政策1","政策2"],"trend":"趋势判断","aggressiveness":0.2,"analysis":"简要分析"}

字段规则:
- sector: 行业/赛道(半导体/新能源/消费/医疗/军工/AI科技/白酒/债市等)
- policyScore: 0-100分(80-100国家战略,60-79有支撑,40-59中性,20-39收紧,0-19打压)
- keyPolicies: 2-4条关联国家政策(十四五数字经济/新质生产力/国产替代/双碳目标等)
- trend: 一句话总结未来1-2年政策趋势
- aggressiveness: -0.5~+0.5(+0.3激进,0中性,-0.3保守)
- analysis: ≤50字

⚠️ 数据纪律: 你的训练知识有截止日期。若用户消息附带了该基金近期走势或大盘实时行情，评分与趋势判断必须优先依据这些真实数据；对记忆中不确定的政策不得编造具体名称与日期，可表述为"基于已知政策框架推断"。"""

MACRO_ANALYSIS_STREAM_PROMPT = """你是宏观经济政策研究员。分析该基金所属行业/赛道，结合当前（{current_date}）中国最新政策评估政策利好程度。

【输出格式 - 严格遵守】
1. 先输出 100-150 字的中文宏观分析（依次说明：行业归属、政策力度评估、关键关联政策、趋势判断、对投资策略的启示）
2. 分析结束后，必须单独输出一行：::JSON::
3. 在 ::JSON:: 之后紧跟一个 JSON 对象，中间不要换行、不要加空格、不要加 markdown

JSON 格式：{"sector":"行业/赛道","policyScore":75,"keyPolicies":["政策1","政策2"],"trend":"趋势判断","aggressiveness":0.2,"analysis":"≤50字点评"}

字段规则:
- sector: 行业/赛道(半导体/新能源/消费/医疗/军工/AI科技/白酒/债市等)
- policyScore: 0-100分(80-100国家战略,60-79有支撑,40-59中性,20-39收紧,0-19打压)
- keyPolicies: 2-4条关联国家政策
- trend: 一句话总结未来1-2年政策趋势
- aggressiveness: -0.5~+0.5(+0.3激进,0中性,-0.3保守)
- analysis: ≤50字

⚠️ 严格规则：
- 中文分析里不要写具体 JSON 字段值
- 不要在分析中用 {{ }} 符号
- 不要 markdown 代码块
- JSON 必须以 { 开头、以 } 结尾，且是完整的单一对象
- 数据纪律：你的训练知识有截止日期。若用户消息附带了该基金近期走势或大盘实时行情，必须优先依据这些真实数据做判断，并在中文分析中引用其中关键数字；对记忆中不确定的政策不得编造具体名称与日期，可表述为"基于已知政策框架推断"。"""


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

        # 动态注入当前精确时间到系统提示词
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
        raw_text = text  # 保留原始内容用于错误日志
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


# ==================== AI 推荐加仓档位 ====================

TIER_RECOMMEND_PROMPT = """你是基金策略师。核心原则：【预算约束 > 数据驱动 > 政策分析】。

【输出结构 - 严格遵守】
你的回复必须分两部分，按顺序输出：

【第一部分：策略分析（400-600字中文）】
写一段 400-600 字的数据驱动策略分析，必须引用用户的真实数据（初始本金、预算剩余金额、当前收益率、当前市值、持有天数等）。按以下顺序展开，每一条都要有"数据+由此得出的判断"：

1. **当前状态诊断**：引用当前收益率、当前市值、初始本金、持有天数，诊断基金当前状态（亏损/盈利/亏多少/赚多少），判断属于什么阶段（深套/浅套/浮盈/牛市中），由此决定采用"越跌越买"还是"上涨回调加仓"策略，并说明理由。

2. **预算框架分析**：把用户的 maxInvestment（投入上限）、totalBuyAmount（已投入）、剩余预算、预算覆盖率（=剩余/初始本金）全部列出来，算出剩余预算能支撑多少比例加仓。判断预算属于充裕/适中/偏紧/紧张，据此确定4档合计买入比例的理想区间。

3. **档位设计逻辑**：基于当前收益率位置，决定首档门槛（跌到多少开始出手）、每档间隔（跌多少加一档）、末档底线（最多跌到哪）。解释为什么选择这个间隔和范围。这里只说设计逻辑和区间概念，不写具体 line/ratio 数值。

4. **宏观政策微调**（如提供宏观分析）：引用政策评分和关键政策，说明政策利好程度对整体策略是偏激进还是偏保守，以及如何在实际档位中体现（上浮/下调/维持）。

5. **止盈止损逻辑**：基于基金类型、当前收益率、持有天数，设定止盈线和止损线的逻辑。解释为什么设这个点位——比如"持有XX天已经，止损线不能设太浅否则白挨打"。

⚠️ 严格规则：
- 文本分析中禁止出现档位的「line/ratio」具体数字和「stopProfitLine/stopLossLine/stopProfitRatio/stopLossRatio」的具体数值。所有具体数值只出现在 JSON 中。
- 你可以写"4档合计买入金额约X元、占剩余预算Y%"，因为这是预算框架的算数结果。
- 不要在分析中用 { } 符号，不要用 markdown。

【第二部分：JSON 策略数据】
在中文分析结束后，必须单独输出一行：::JSON::
然后在 ::JSON:: 之后紧跟 JSON 对象，中间不要换行、不要加空格、不要 markdown 代码块。要求：
1. 只能输出一个 JSON 对象
2. 字符串内部用「」代替 ASCII 双引号
3. JSON 必须以 { 开头，以 } 结尾
4. 不要 markdown 包裹

JSON 格式（示例值，请按实际数据生成）：
{"strategyType":"downside","tiers":[{"line":-8,"ratio":5},{"line":-13,"ratio":10},{"line":-19,"ratio":18},{"line":-26,"ratio":30}],"pullbackTiers":[],"stopProfitLine":25,"stopLossLine":-30,"stopProfitRatio":20,"stopLossRatio":60,"strategyStyle":"预算充裕型","explanation":"..."}

【策略选择】收益率≤0→strategyType="downside"(越跌越买,tiers为主,pullbackTiers=[])；收益率>0→strategyType="pullback"(回调加仓,tiers作安全网,pullbackTiers为主)。

【预算框架(硬约束)】ratio总和(小数)×初始本金 ≤ 剩余预算。覆盖率=剩余预算/初始本金。覆盖率越高越要大胆：
≥10倍→4档之和100-500%+，合计买入金额应占剩余预算30-50%以上
5-10倍→4档之和80-200%，合计金额占剩余预算20-40%
2-5倍→4档之和50-100%，合计金额占剩余预算10-25%
1-2倍→30-60%  0.5-1倍→15-30%  <0.5倍→≤15%  未设置→视为充裕
⚠️ 覆盖率越高越要大胆，预算不充分利用是最大浪费！

【档位设计】tiers: line从-6~-10%起步均匀分布，末档≤-35%，间隔4-8%，ratio逐档递增(末档是首档3-6倍)。pullbackTiers: line为-2~-18%从浅到深，绝对值不超过当前收益率。

【宏观微调(辅助)】在预算框架内微调：policyScore≥80→比例上浮10-20%+间隔缩小1-2%；40-79→维持；<40→比例下调10-20%+间隔拉大1-2%。

【估值与回测(如提供)】若用户消息附带指数估值分位与档位回测数据，必须参考：
- 估值分位>70%(偏高估)→档位整体偏保守，首档更深、比例取区间下限；30-70%(合理)→正常；<30%(偏低估)→可积极，首档更浅、比例取区间上限。
- 回测资金利用率<50%→说明末档过深从未触发，收窄档距；策略收益明显跑输一次性持有→调整档位深度或比例分配。
- 策略分析文本第4条中引用估值分位和回测结论各一句。

【止盈止损】stopProfitLine: 股基15-35%,债基5-10%,持有<30天偏低。stopLossLine: 股基-20~-35%,保守型-15~-20%。stopProfitRatio: 15-30%。stopLossRatio: 50-80%。

【style/explanation】strategyStyle选:"上涨回调型"/"预算充裕型"/"预算平衡型"/"保守防御型"。explanation≤100字: 策略选择→预算约束→比例逻辑→宏观微调(如适用)→止盈止损。pullback策略需解释为何回调加仓。"""


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
    AI 根据基金情况 + 宏观政策分析，推荐合理的金字塔加仓档位 + 止盈止损

    Args:
        macro_analysis: 宏观政策分析结果，由 analyze_fund_macro() 返回
        market_context: 实时市场数据 + 回测结论文本（估值分位、档位回测等）

    Returns:
        {"tiers": [...], "stopProfitLine": float, "stopLossLine": float,
         "stopProfitRatio": float, "stopLossRatio": float,
         "strategyStyle": str, "explanation": str}
    """
    try:
        remaining = max_investment - total_buy_amount if max_investment > 0 else float("inf")

        # 计算预算覆盖率（剩余预算 / 初始本金），帮助 LLM 判断预算充裕程度
        if max_investment > 0 and initial_principal > 0:
            coverage_ratio = remaining / initial_principal
            coverage_desc = (
                "极其充裕，请大胆推荐高位加仓！" if coverage_ratio >= 10 else
                "非常充裕，可大幅提高加仓比例" if coverage_ratio >= 5 else
                "充裕（可积极配置）" if coverage_ratio >= 2.0 else
                "适中" if coverage_ratio >= 1.0 else
                "偏紧" if coverage_ratio >= 0.5 else
                "紧张（需保守）"
            )
            remaining_str = f"¥{remaining:,.0f}"

            # 高覆盖率时额外强调，让 AI 不要保守
            bold_hint = ""
            if coverage_ratio >= 10:
                bold_hint = (
                    f"\n⚠️⚠️⚠️ 注意：预算覆盖率高达{coverage_ratio:.0f}倍！"
                    f"用户设了 ¥{max_investment:,.0f} 的上限，目前只投了 ¥{total_buy_amount:,.0f}，"
                    f"剩余 ¥{remaining:,.0f} 几乎没动。请务必大胆推荐高额加仓，4档总和至少{initial_principal * 1.0:,.0f}元起，"
                    f"不要推荐像 5%、10% 这种杯水车薪的比例！"
                )
            elif coverage_ratio >= 5:
                bold_hint = (
                    f"\n⚠️⚠️ 注意：预算覆盖率{coverage_ratio:.0f}倍，空间很大。"
                    f"用户当前只投了 ¥{total_buy_amount:,.0f}，还有 ¥{remaining:,.0f} 预算。"
                    f"请大胆提高加仓比例，不要过于保守！"
                )

            budget_info = (
                f"投入上限：¥{max_investment:,.2f}\n"
                f"已投入金额：¥{total_buy_amount:,.2f}\n"
                f"剩余可投入预算：{remaining_str}（预算覆盖率 = 剩余预算/初始本金 = {coverage_ratio:.1f}倍，预算状态：{coverage_desc}）"
                f"{bold_hint}"
            )
        else:
            remaining_str = "无上限（未设置最大投入）"
            budget_info = (
                f"投入上限：未设置\n"
                f"已投入金额：¥{total_buy_amount:,.2f}\n"
                f"剩余可投入预算：无上限（预算覆盖率视为无穷大，可积极配置）"
            )

        # 构建宏观分析部分（放在预算信息之后，表明其为辅助参考）
        macro_text = ""
        if macro_analysis and macro_analysis.get("sector") != "未知":
            policies = "、".join(macro_analysis.get("keyPolicies", [])) or "暂无明确关联政策"
            aggressiveness = macro_analysis.get('aggressiveness', 0)
            if aggressiveness > 0.15:
                policy_advice = "可在预算框架内小幅上浮比例（+10~20%）"
            elif aggressiveness < -0.15:
                policy_advice = "可在预算框架内小幅下调比例（-10~20%）"
            else:
                policy_advice = "维持预算框架，不做系统性调整"
            macro_text = (
                f"\n\n📎 以下为宏观政策分析（辅助参考，仅在预算允许范围内做微调）：\n"
                f"所属行业/赛道：{macro_analysis.get('sector', '未知')}\n"
                f"政策支持评分：{macro_analysis.get('policyScore', 50)}/100\n"
                f"关联国家政策：{policies}\n"
                f"政策趋势：{macro_analysis.get('trend', '')}\n"
                f"调整建议：{policy_advice}（调整系数 {aggressiveness:+.1f}）\n"
            )

        # 高预算覆盖率时的醒目提醒
        if max_investment > 0 and initial_principal > 0:
            cov = remaining / initial_principal
            bold_prefix = ""
            if cov >= 10:
                bold_prefix = "⚠️⚠️⚠️ 重要：用户预算极其充裕（覆盖率 {}倍）！不要建议保守的5%、10%比例，请大胆把档位比例设高，让用户充分用上预算！\n\n".format(int(cov))
            elif cov >= 5:
                bold_prefix = "⚠️⚠️ 注意：用户预算很充裕（覆盖率 {}倍），加仓比例可以大胆一些。\n\n".format(int(cov))
        else:
            bold_prefix = ""

        # 实时市场数据 + 回测结论（估值分位、档位有效性验证）
        market_text = ""
        if market_context:
            market_text = (
                f"\n\n📊 以下为实时市场数据与当前档位参数的历史回测（真实数据，请认真参考）：\n"
                f"{market_context}\n"
            )

        user_message = (
            f"请为以下基金推荐 4 档金字塔加仓方案和止盈止损线。\n"
            f"记住：先看预算决定比例框架，再用宏观分析微调。\n"
            f"{bold_prefix}"
            f"基金名称：{fund_name}\n"
            f"初始本金：¥{initial_principal:,.2f}\n"
            f"{budget_info}\n"
            f"当前收益率：{current_return_rate:.2f}%\n"
            f"当前市值：¥{current_market_value:,.2f}\n"
            f"已持有天数：{hold_days}天"
            f"{macro_text}"
            f"{market_text}"
        )

        messages = [
            {"role": "system", "content": TIER_RECOMMEND_PROMPT},
            {"role": "user", "content": user_message},
        ]

        # 带重试的 LLM 调用 + 安全 JSON 解析
        text = _call_llm_with_retry(messages, temperature=0.3, max_tokens=2000)
        try:
            result = _safe_parse_json(text)
        except json.JSONDecodeError:
            # 安全解析失败，尝试暴力兜底
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
        # _brute_parse_json 也没提取到 tiers
        logger.error("AI 推荐档位解析失败（缺少关键字段）: %s, 原始: %s", e, text[:500])
        raise RuntimeError("AI 返回格式异常，请重试")
    except Exception as e:
        logger.error("AI 推荐档位失败: %s", e)
        raise RuntimeError(f"AI 服务暂时不可用: {e}")


def _build_recommend_user_message(
    fund_name, total_buy_amount, initial_principal, max_investment,
    current_return_rate, current_market_value, hold_days, macro_analysis,
    market_context="",
):
    """构建加仓档位推荐的 user message（复用）"""
    remaining = max_investment - total_buy_amount if max_investment > 0 else float("inf")
    if max_investment > 0 and initial_principal > 0:
        coverage_ratio = remaining / initial_principal
        coverage_desc = (
            "极其充裕，请大胆推荐高位加仓！" if coverage_ratio >= 10 else
            "非常充裕，可大幅提高加仓比例" if coverage_ratio >= 5 else
            "充裕（可积极配置）" if coverage_ratio >= 2.0 else
            "适中" if coverage_ratio >= 1.0 else
            "偏紧" if coverage_ratio >= 0.5 else
            "紧张（需保守）"
        )
        remaining_str = f"¥{remaining:,.0f}"
        bold_hint = ""
        if coverage_ratio >= 10:
            bold_hint = (
                f"\n⚠️⚠️⚠️ 注意：预算覆盖率高达{coverage_ratio:.0f}倍！"
                f"用户设了 ¥{max_investment:,.0f} 的上限，目前只投了 ¥{total_buy_amount:,.0f}，"
                f"剩余 ¥{remaining:,.0f} 几乎没动。请务必大胆推荐高额加仓，4档总和至少{initial_principal * 1.0:,.0f}元起，"
                f"不要推荐像 5%、10% 这种杯水车薪的比例！"
            )
        elif coverage_ratio >= 5:
            bold_hint = (
                f"\n⚠️⚠️ 注意：预算覆盖率{coverage_ratio:.0f}倍，空间很大。"
                f"用户当前只投了 ¥{total_buy_amount:,.0f}，还有 ¥{remaining:,.0f} 预算。"
                f"请大胆提高加仓比例，不要过于保守！"
            )
        budget_info = (
            f"投入上限：¥{max_investment:,.2f}\n"
            f"已投入金额：¥{total_buy_amount:,.2f}\n"
            f"剩余可投入预算：{remaining_str}（预算覆盖率 = 剩余预算/初始本金 = {coverage_ratio:.1f}倍，预算状态：{coverage_desc}）"
            f"{bold_hint}"
        )
    else:
        budget_info = (
            f"投入上限：未设置\n"
            f"已投入金额：¥{total_buy_amount:,.2f}\n"
            f"剩余可投入预算：无上限（预算覆盖率视为无穷大，可积极配置）"
        )

    macro_text = ""
    if macro_analysis and macro_analysis.get("sector") != "未知":
        policies = "、".join(macro_analysis.get("keyPolicies", [])) or "暂无明确关联政策"
        aggressiveness = macro_analysis.get('aggressiveness', 0)
        if aggressiveness > 0.15:
            policy_advice = "可在预算框架内小幅上浮比例（+10~20%）"
        elif aggressiveness < -0.15:
            policy_advice = "可在预算框架内小幅下调比例（-10~20%）"
        else:
            policy_advice = "维持预算框架，不做系统性调整"
        macro_text = (
            f"\n\n📎 以下为宏观政策分析（辅助参考，仅在预算允许范围内做微调）：\n"
            f"所属行业/赛道：{macro_analysis.get('sector', '未知')}\n"
            f"政策支持评分：{macro_analysis.get('policyScore', 50)}/100\n"
            f"关联国家政策：{policies}\n"
            f"政策趋势：{macro_analysis.get('trend', '')}\n"
            f"调整建议：{policy_advice}（调整系数 {aggressiveness:+.1f}）\n"
        )

    if max_investment > 0 and initial_principal > 0:
        cov = remaining / initial_principal
        bold_prefix = ""
        if cov >= 10:
            bold_prefix = "⚠️⚠️⚠️ 重要：用户预算极其充裕（覆盖率 {}倍）！不要建议保守的5%、10%比例，请大胆把档位比例设高，让用户充分用上预算！\n\n".format(int(cov))
        elif cov >= 5:
            bold_prefix = "⚠️⚠️ 注意：用户预算很充裕（覆盖率 {}倍），加仓比例可以大胆一些。\n\n".format(int(cov))
    else:
        bold_prefix = ""

    # 收益率状态诊断
    r = current_return_rate
    if r <= -30:
        status_label = "深度亏损（-30%以下）- 已严重被套，策略应偏向防守，止损不必太近"
    elif r <= -15:
        status_label = "中度亏损（-15%~-30%）- 有一定跌幅，适合金字塔加仓拉低成本"
    elif r <= -5:
        status_label = "浅度亏损（-5%~-15%）- 小幅浮亏，策略适中"
    elif r <= 0:
        status_label = "微亏（0%~-5%）- 接近成本线，可适度乐观"
    elif r <= 10:
        status_label = "小幅盈利（0%~10%）- 已有利润，可考虑回调加仓策略"
    elif r <= 30:
        status_label = "可观盈利（10%~30%）- 利润可观，应以回调加仓+守住利润为主"
    else:
        status_label = "大幅盈利（30%以上）- 浮盈丰厚，需重点设置止盈保护"

    # 持有天数解读
    h = hold_days
    if h <= 30:
        hold_label = "持有时间很短（≤1个月），属于新入场，策略可相对积极"
    elif h <= 180:
        hold_label = f"持有{h}天（约{h//30}个月），属于中期持有，策略应稳健为主"
    elif h <= 365:
        hold_label = f"持有{h}天（约{h//30}个月），已持有一段时间，止盈止损需考虑时间成本"
    else:
        hold_label = f"持有{h}天（超过1年），属长期持有，应有足够耐心，止盈止损可设宽一些"

    # 实时市场数据 + 回测结论（估值分位、档位有效性验证）
    market_text = ""
    if market_context:
        market_text = (
            f"\n\n📊 以下为实时市场数据与当前档位参数的历史回测（真实数据，请认真参考）：\n"
            f"{market_context}\n"
        )

    return (
        f"请为以下基金推荐 4 档金字塔加仓方案和止盈止损线。\n"
        f"\n"
        f"=== 核心数据 ===\n"
        f"基金名称：{fund_name}\n"
        f"初始本金：¥{initial_principal:,.2f}\n"
        f"当前市值：¥{current_market_value:,.2f}\n"
        f"当前收益率：{current_return_rate:.2f}% => {status_label}\n"
        f"已持有天数：{hold_days}天 => {hold_label}\n"
        f"\n"
        f"=== 预算状况 ===\n"
        f"{budget_info}\n"
        f"\n"
        f"=== 设计要点 ===\n"
        f"1. 先看收益率和持有天数判断当前所处阶段 → 决定策略类型和首档门槛\n"
        f"2. 再看预算覆盖率决定4档合计买入比例区间 → 决定是大胆加还是保守加\n"
        f"3. 最后参考宏观政策做微调（上浮或下调10-20%）\n"
        f"4. 止盈止损要根据当前收益率位置和持有天数来定——套太深止损别太近，浮盈多止盈要积极\n"
        f"{macro_text}"
        f"{market_text}"
    )


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
    """流式版：AI 推荐加仓档位（生成器），返回原始 LLM 流式输出，调用方自行解析 JSON"""
    user_message = _build_recommend_user_message(
        fund_name, total_buy_amount, initial_principal, max_investment,
        current_return_rate, current_market_value, hold_days, macro_analysis,
        market_context,
    )
    messages = [
        {"role": "system", "content": TIER_RECOMMEND_PROMPT},
        {"role": "user", "content": user_message},
    ]
    yield from _call_llm_stream(messages, temperature=0.3, max_tokens=2000)


# ==================== AI 操作评价 ====================

EVALUATE_OPERATION_PROMPT = """你是一位经验丰富的基金投资行为分析师。用户每次买卖操作后，需要你对这次操作进行客观评价。

评价维度：
1. **操作时机**：当前收益率下，这个操作是否合适？
2. **金额合理性**：投入/卖出的金额占总仓位比例是否合理？
3. **纪律性**：是否遵循了止盈止损等纪律，还是情绪化操作？
4. **风险提示**：后续需要注意的风险点

评价要求：
- 语气客观理性，像一位有经验的投资教练在点评
- 不模棱两可，要给出明确的"做得对/不太对"的判断
- 最后给出 1-2 条具体的改进建议
- 整体控制在 150 字以内
- 用纯文本回复，不需要 JSON 格式"""


# ==================== AI 整体组合分析 ====================

OVERALL_ANALYSIS_PROMPT = """你是一位资深的基金投资组合分析师。用户有一篮子基金持仓，请根据所有基金的详细数据，对整体组合进行系统性分析并给出具体操作建议。

分析维度（必须覆盖）：
1. **组合总览**：总市值、总本金、总收益率、盈亏金额、基金数量等关键指标总结
2. **持仓结构诊断**：分析持仓的分散程度、单只集中度风险、是否存在仓位过重/过轻的问题
3. **逐个基金诊断**：对每只基金给出状态判断（健康/关注/警戒/危险），说明理由
4. **操作建议**：针对每只基金给出具体操作建议（继续持有/逢高减仓/止损离场/逢低加仓/按计划加仓等），以及建议的理由
5. **整体策略调整**：如果整体组合存在问题（如过度集中、风格过于单一等），给出调整方向

回复要求：
- 用中文回复，语气专业务实、像一个有经验的投资顾问在给朋友分析
- 每条建议要有数据支撑，结合当前收益率、今日涨跌、持有天数等具体数据
- 不预测市场涨跌，只做风险评估和策略建议
- 控制在 600-1000 字之间
- 用纯文本回复，不需要 JSON 格式"""


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




