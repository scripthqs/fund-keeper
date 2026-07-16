"""AI Agent 层 - 投资顾问 Agent 与情绪文案生成"""

import base64
import io
import json
import logging
from typing import Dict, List, Optional

from openai import OpenAI
from PIL import Image

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


# ==================== 图片压缩 ====================

def _compress_image_base64(image_base64: str, max_size: int = 1920, quality: int = 85) -> str:
    """
    压缩 base64 图片，控制大小和分辨率。
    返回压缩后的 base64 data URL。
    """
    if not image_base64 or not image_base64.startswith("data:image"):
        return image_base64

    try:
        # 分离 data URL 前缀
        header, encoded = image_base64.split(",", 1)
        img_bytes = base64.b64decode(encoded)
        img = Image.open(io.BytesIO(img_bytes))

        # 转换为 RGB（去除透明通道）
        if img.mode in ("RGBA", "P"):
            img = img.convert("RGB")

        # 等比例缩放
        w, h = img.size
        if w > max_size or h > max_size:
            ratio = min(max_size / w, max_size / h)
            new_size = (int(w * ratio), int(h * ratio))
            img = img.resize(new_size, Image.LANCZOS)

        # 压缩为 JPEG
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=quality, optimize=True)
        compressed = base64.b64encode(buf.getvalue()).decode("utf-8")
        return f"data:image/jpeg;base64,{compressed}"
    except Exception as e:
        logger.warning("图片压缩失败，使用原图: %s", e)
        return image_base64


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

DAILY_PARSE_IMAGE_PROMPT = """你是一个数据解析助手。用户上传了基金持仓截图。
你需要从截图中识别出各基金的涨跌情况数据。

**重要规则：**
1. 从截图中识别基金名称、今日涨跌幅等关键数据
2. 只解析"用户基金列表"中明确存在的基金（通过名称模糊匹配）
3. 如果截图中的基金不在用户列表中，忽略它
4. todayChange 是涨跌幅百分比，正数表示上涨，负数表示下跌
5. 如果没有文字描述，仅凭截图数据，为能识别的每只基金输出
6. 只返回纯 JSON 数组，不要包含任何 markdown 标记或额外文字"""

SCREENSHOT_SYNC_PROMPT = """你是一个基金数据提取助手。用户上传了基金持仓截图。

你需要从截图中识别出**所有**基金的完整持仓数据，包括：
- 基金名称
- 当前持仓市值/金额
- 持仓收益率（总收益率）
- 持有份额（如有）
- 今日涨跌幅（如有）
- 累计收益/盈亏金额（如有）
- 买入金额/本金（如有）

**重要规则：**
1. 从截图中识别每只基金的完整数据，无论该基金是否已在用户列表中
2. 对于每只识别到的基金，尽可能多地提取数据字段
3. 如果某些字段在截图中没有，就设为 0 或 null
4. 金额统一为"元"为单位，如果是"万元"请乘以 10000 转换
5. 收益率是百分比数值，如 15.5 表示 15.5%
6. 当前市值 currentMarketValue 是必填字段（这是最重要的数据）
7. 只返回纯 JSON 数组，不要包含任何 markdown 标记或额外文字"""

SCREENSHOT_SYNC_OUTPUT_FORMAT = """请返回 JSON 数组，每个元素格式：
{
  "name": "基金名称",
  "currentMarketValue": 当前市值(元),
  "currentReturnRate": 持仓收益率(百分比数值),
  "todayChange": 今日涨跌幅(百分比数值, 无则为0),
  "totalBuyAmount": 累计买入金额(元, 无则为0),
  "initialPrincipal": 初始本金(元, 无则等于currentMarketValue),
  "buyDate": "买入日期(YYYY-MM-DD格式, 无则为空字符串)"
}"""


def parse_daily_data(
    user_message: str,
    funds: List[dict],
    image_base64: Optional[str] = None,
) -> List[dict]:
    """
    智能解析用户每日收益的自然语言描述（支持截图识图）

    Args:
        user_message: 用户自然语言消息，如 "今天白酒涨了2%，医疗跌了1.5%"（截图时可空）
        funds: 基金列表 [{"id": "xxx", "name": "白酒", "currentReturnRate": 10.5}, ...]
        image_base64: 可选，base64 编码的截图数据 (data:image/png;base64,...)

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

        has_image = bool(image_base64)

        system_content = DAILY_PARSE_IMAGE_PROMPT if has_image else DAILY_PARSE_PROMPT

        # 构建用户消息内容
        if has_image:
            # 多模态：图片 + 文字（压缩图片避免 API 限制）
            compressed_image = _compress_image_base64(image_base64, max_size=1280, quality=80)
            text_parts = [f"用户基金列表：\n{fund_list_text}"]
            if user_message.strip():
                text_parts.append(f"附加说明：{user_message}")
            text_parts.append(
                '请识别截图中的数据，返回 JSON 数组，格式：[{"fundId":"基金ID","fundName":"基金名称","todayChange":涨跌幅百分比}]'
            )
            user_content = [
                {"type": "text", "text": "\n\n".join(text_parts)},
                {"type": "image_url", "image_url": {"url": compressed_image}},
            ]
            model = settings.vision_model
            extra_kwargs = {"temperature": 0.1, "max_tokens": 2048}
        else:
            user_content = (
                f"用户基金列表：\n{fund_list_text}\n\n"
                f"用户消息：{user_message}\n\n"
                f'请返回 JSON 数组，格式：[{{"fundId":"基金ID","fundName":"基金名称","todayChange":涨跌幅百分比}}]'
            )
            model = settings.LLM_MODEL
            extra_kwargs = {}

        messages = [
            {"role": "system", "content": system_content},
            {"role": "user", "content": user_content},
        ]

        response = client.chat.completions.create(
            model=model,
            messages=messages,
            **extra_kwargs,
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


# ==================== 截图同步解析（完整持仓数据） ====================

def parse_screenshot_for_sync(
    image_base64: str,
    existing_funds: List[dict],
) -> dict:
    """
    从基金持仓截图中识别完整持仓数据，并与现有基金匹配，
    返回变更预览（新增/修改的基金及其数据变化）

    Args:
        image_base64: base64 编码的截图 (data:image/...;base64,...)
        existing_funds: 现有基金列表 [{"id":"xx","name":"白酒","currentMarketValue":10000,...}, ...]

    Returns:
        {
            "matches": [  # AI 识别结果与现有基金的匹配
                {"fundId":"xx", "fundName":"白酒", "matched":true,
                 "oldData":{...}, "newData":{...}, "changes":["市值:10000→12000",...]},
            ],
            "newFunds": [  # 截图中存在但本地没有的新基金
                {"name":"新能源", "currentMarketValue":5000, "currentReturnRate":8.5, ...}
            ],
            "unchanged": [{"fundId":"xx", "fundName":"医疗"}]  # 未识别到变化
        }
    """
    try:
        client = _get_client()

        # 压缩图片（DeepSeek 等 API 对图片大小有限制）
        compressed_image = _compress_image_base64(image_base64, max_size=1280, quality=80)

        # 构建现有基金列表文本（供 AI 匹配用）
        existing_text = ""
        if existing_funds:
            lines = []
            for f in existing_funds:
                lines.append(
                    f"- {f['name']}（ID:{f['id']}，市值:{f.get('currentMarketValue',0):.0f}，"
                    f"收益率:{f.get('currentReturnRate',0):.1f}%）"
                )
            existing_text = "用户已有基金列表：\n" + "\n".join(lines)

        user_text = f"{existing_text}\n\n{SCREENSHOT_SYNC_OUTPUT_FORMAT}"

        messages = [
            {"role": "system", "content": SCREENSHOT_SYNC_PROMPT},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": user_text},
                    {"type": "image_url", "image_url": {"url": compressed_image}},
                ],
            },
        ]

        # 使用支持多模态的模型（deepseek-v4-pro 原生支持 vision）
        model = settings.LLM_VISION_MODEL or settings.LLM_MODEL

        response = client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=0.1,
            max_tokens=4096,
        )
        text = response.choices[0].message.content.strip()
        logger.info("截图同步 AI 原始返回: %s", text[:500])

        # 提取 JSON
        if "```" in text:
            start = text.find("[")
            end = text.rfind("]")
            if start != -1 and end != -1:
                text = text[start:end + 1]

        recognized = json.loads(text)
        if not isinstance(recognized, list):
            logger.warning("截图同步 AI 返回不是数组: %s", text)
            return {"matches": [], "newFunds": [], "unchanged": []}

        # 与现有基金做匹配
        return _match_recognized_funds(recognized, existing_funds)

    except RuntimeError:
        raise
    except json.JSONDecodeError as e:
        logger.error("截图同步 JSON 解析失败: %s", e)
        return {"matches": [], "newFunds": [], "unchanged": [], "error": f"AI 返回解析失败: {e}"}
    except Exception as e:
        logger.error("截图同步解析失败: %s", e)
        # 返回结构化错误，不要抛 RuntimeError（避免 500）
        err_msg = str(e)
        if "400" in err_msg or "calculation tool" in err_msg:
            return {
                "matches": [],
                "newFunds": [],
                "unchanged": [],
                "error": "AI 识图服务暂时不可用（可能是图片过大或模型不支持），请尝试文字描述方式录入",
            }
        raise RuntimeError(f"截图识别服务异常: {e}")


def _match_recognized_funds(recognized: list, existing_funds: list) -> dict:
    """
    将 AI 识别结果与现有基金做模糊匹配，
    生成变更预览数据
    """
    matches = []
    new_funds = []
    unchanged = []
    matched_existing_ids = set()

    for rec in recognized:
        rec_name = (rec.get("name") or "").strip()
        if not rec_name:
            continue

        # 模糊匹配现有基金
        best_match = None
        best_score = 0
        for ef in existing_funds:
            ef_name = (ef.get("name") or "").strip()
            # 简单包含匹配
            score = 0
            if rec_name == ef_name:
                score = 100
            elif rec_name in ef_name or ef_name in rec_name:
                score = 80
            elif any(w in ef_name for w in rec_name if len(w) >= 2):
                score = 60
            if score > best_score:
                best_score = score
                best_match = ef

        if best_match and best_score >= 60:
            # 已匹配到现有基金 → 计算变更
            fund_id = best_match["id"]
            matched_existing_ids.add(fund_id)

            new_data = {
                "name": rec_name,
                "currentMarketValue": _safe_float(rec.get("currentMarketValue")),
                "currentReturnRate": _safe_float(rec.get("currentReturnRate")),
                "todayChange": _safe_float(rec.get("todayChange")),
                "totalBuyAmount": _safe_float(rec.get("totalBuyAmount")),
                "initialPrincipal": _safe_float(rec.get("initialPrincipal")),
                "buyDate": rec.get("buyDate", ""),
            }

            old_data = {
                "name": best_match.get("name", ""),
                "currentMarketValue": _safe_float(best_match.get("currentMarketValue")),
                "currentReturnRate": _safe_float(best_match.get("currentReturnRate")),
                "totalBuyAmount": _safe_float(best_match.get("totalBuyAmount")),
                "totalSellAmount": _safe_float(best_match.get("totalSellAmount")),
                "initialPrincipal": _safe_float(best_match.get("initialPrincipal")),
                "buyDate": best_match.get("buyDate", ""),
            }

            changes = _compute_changes(old_data, new_data)

            matches.append({
                "fundId": fund_id,
                "fundName": rec_name,
                "matched": True,
                "oldData": old_data,
                "newData": new_data,
                "changes": changes,
            })
        else:
            # 新基金
            new_funds.append({
                "name": rec_name,
                "currentMarketValue": _safe_float(rec.get("currentMarketValue")),
                "currentReturnRate": _safe_float(rec.get("currentReturnRate")),
                "todayChange": _safe_float(rec.get("todayChange")),
                "totalBuyAmount": _safe_float(rec.get("totalBuyAmount")),
                "initialPrincipal": _safe_float(rec.get("initialPrincipal")),
                "buyDate": rec.get("buyDate", ""),
            })

    # 未变化的基金（不在匹配列表中的）
    for ef in existing_funds:
        if ef["id"] not in matched_existing_ids:
            unchanged.append({
                "fundId": ef["id"],
                "fundName": ef.get("name", ""),
            })

    return {
        "matches": matches,
        "newFunds": new_funds,
        "unchanged": unchanged,
    }


def _safe_float(val):
    """安全转换为 float"""
    if val is None:
        return 0
    try:
        return round(float(val), 2)
    except (ValueError, TypeError):
        return 0


def _compute_changes(old_data: dict, new_data: dict) -> list:
    """对比新旧数据，生成变更描述列表"""
    changes = []
    fields = [
        ("currentMarketValue", "市值"),
        ("currentReturnRate", "收益率"),
        ("totalBuyAmount", "累计买入"),
        ("initialPrincipal", "初始本金"),
        ("buyDate", "买入日期"),
    ]
    for key, label in fields:
        old_val = old_data.get(key)
        new_val = new_data.get(key)
        if key == "buyDate":
            if new_val and new_val != old_val and new_val != "":
                changes.append(f"{label}: {old_val or '无'} → {new_val}")
        elif new_val and new_val != old_val and new_val != 0:
            if key == "currentReturnRate":
                changes.append(f"{label}: {old_val:.1f}% → {new_val:.1f}%")
            else:
                changes.append(f"{label}: ¥{old_val:,.0f} → ¥{new_val:,.0f}")
    return changes
