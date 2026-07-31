"""AI 聊天与情绪文案路由"""

import asyncio
import json
import logging
from typing import List

from fastapi import APIRouter, HTTPException, Depends, Header
from fastapi.responses import StreamingResponse

from app.agent import chat_with_advisor, chat_with_advisor_stream, generate_emotion, generate_emotion_stream, interpret_advice, interpret_advice_stream
from app.agent.tools import TOOL_DEFINITIONS, execute_tool
from app.config import settings
from app.database import get_db, gen_id, now_str, get_current_user_id
from app.models import (
    AdviceInterpretRequest,
    AdviceInterpretResponse,
    ChatMessage,
    ChatRequest,
    ChatResponse,
    EmotionRequest,
    EmotionResponse,
)

router = APIRouter(prefix="/api", tags=["AI 对话"])
logger = logging.getLogger(__name__)


async def _uid(x_username: str = Header(None, alias="X-Username")):
    return get_current_user_id(x_username)


# ==================== 聊天消息管理 ====================

@router.get("/chat/messages", response_model=List[ChatMessage])
async def list_chat_messages(user_id: str = Depends(_uid)):
    """获取当前用户的所有聊天记录"""
    conn = get_db()
    rows = conn.execute(
        "SELECT role, content FROM chat_messages WHERE user_id = ? ORDER BY created_at",
        (user_id,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


@router.delete("/chat/messages")
async def clear_chat_messages(user_id: str = Depends(_uid)):
    """清空当前用户的所有聊天记录"""
    conn = get_db()
    conn.execute("DELETE FROM chat_messages WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()
    return {"ok": True}


# ==================== AI 对话 ====================

@router.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest, user_id: str = Depends(_uid)):
    """与 AI 投资顾问对话"""
    if not settings.llm_configured:
        raise HTTPException(
            status_code=503,
            detail="服务端未配置 LLM API Key，请在 .env 文件中设置 LLM_API_KEY",
        )

    # 保存用户消息
    conn = get_db()
    msg_id = gen_id()
    conn.execute(
        "INSERT INTO chat_messages (id, role, content, created_at, user_id) VALUES (?, ?, ?, ?, ?)",
        (msg_id, "user", req.message, now_str(), user_id),
    )
    conn.commit()
    conn.close()

    # 调用 AI
    try:
        history_dicts = [{"role": m.role, "content": m.content} for m in req.history]
        reply = chat_with_advisor(
            user_message=req.message,
            fund_context=req.fund_context,
            history=history_dicts,
        )
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))

    # 保存 AI 回复
    conn = get_db()
    ai_id = gen_id()
    conn.execute(
        "INSERT INTO chat_messages (id, role, content, created_at, user_id) VALUES (?, ?, ?, ?, ?)",
        (ai_id, "assistant", reply, now_str(), user_id),
    )
    conn.commit()
    conn.close()

    return ChatResponse(reply=reply)


@router.post("/chat/stream")
async def chat_stream(req: ChatRequest, user_id: str = Depends(_uid)):
    """与 AI 投资顾问对话（流式 SSE）"""
    if not settings.llm_configured:
        raise HTTPException(status_code=503, detail="服务端未配置 LLM API Key")

    # 保存用户消息
    conn = get_db()
    msg_id = gen_id()
    conn.execute(
        "INSERT INTO chat_messages (id, role, content, created_at, user_id) VALUES (?, ?, ?, ?, ?)",
        (msg_id, "user", req.message, now_str(), user_id),
    )
    conn.commit()
    conn.close()

    history_dicts = [{"role": m.role, "content": m.content} for m in req.history]

    async def event_stream():
        import threading
        from queue import Queue as TQueue

        full_reply = ""
        chunk_queue = TQueue()
        error_holder = []

        def _run():
            try:
                for chunk in chat_with_advisor_stream(
                    user_message=req.message,
                    fund_context=req.fund_context,
                    history=history_dicts,
                ):
                    chunk_queue.put(chunk)
            except Exception as e:
                error_holder.append(e)
            finally:
                chunk_queue.put(None)  # 结束标志

        thread = threading.Thread(target=_run, daemon=True)
        thread.start()

        loop = asyncio.get_running_loop()
        while True:
            chunk = await loop.run_in_executor(None, chunk_queue.get)
            if chunk is None:
                break
            full_reply += chunk
            yield f"data: {json.dumps({'content': chunk}, ensure_ascii=False)}\n\n"

        thread.join(timeout=5)

        if error_holder:
            logger.error("流式对话失败: %s", error_holder[0])
            yield f"data: {json.dumps({'error': str(error_holder[0]), 'done': True}, ensure_ascii=False)}\n\n"
            return

        # 流式完成后保存 AI 回复
        ai_id = gen_id()
        conn2 = get_db()
        conn2.execute(
            "INSERT INTO chat_messages (id, role, content, created_at, user_id) VALUES (?, ?, ?, ?, ?)",
            (ai_id, "assistant", full_reply, now_str(), user_id),
        )
        conn2.commit()
        conn2.close()

        yield f"data: {json.dumps({'content': '', 'done': True, 'messageId': ai_id}, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


# ==================== 智能对话（Function Calling） ====================

SMART_CHAT_SYSTEM_PROMPT = """你是「理财小助手」，一个专业、亲切的 AI 基金投资管家。

## 核心能力（必须记住）
- ✅ **你可以联网搜索**：通过 search_web 工具实时搜索最新新闻、政策、行情、基金资讯
- ✅ **你可以查看持仓**：调用工具获取用户实时的基金持仓数据
- ✅ **你可以执行交易**：帮用户买入、卖出基金（需用户确认）
- ⚠️ 以上所有能力都是真实的，当用户问「你能联网吗」「你能查数据吗」，回答「可以」

## 你是谁
- 你服务于持有中国公募基金的个人投资者
- 你的目标是帮助用户做出理性、数据驱动的投资决策

## 性格与语气
- 像一位有10年经验的资深理财顾问朋友，专业但不端着
- 回答简洁有重点，多用户真正关心的数据，少废话
- 适当使用 emoji 增加亲和力（每段不超过2个）
- 遇到用户恐慌时先安抚情绪，再用数据说话
- 永远不预测具体涨跌，只说概率和风险

## 工具使用规则
你有以下工具可以调用，必须严格遵守使用场景：

1. **get_holdings_summary** — 用户问「持仓」「概况」「我的基金」时调用
2. **get_fund_detail** — 用户问某只具体基金的详细信息时调用
3. **check_alerts** — 用户问「预警」「风险」「要不要卖」时调用
4. **get_trading_suggestions** — 用户问「建议」「该怎么办」「操作策略」时调用
5. **update_all_nav** — 用户要查询最新净值、涨跌幅时调用（仅获取实时数据，不会修改持仓）。⚠️ 回复时第一句必须是总体汇总（总市值、今日预估总盈亏、总体涨跌幅），然后再列各基金明细。工具返回中已包含「📌 总体预估」行，你必须把它放在回复最前面，禁止省略
6. **get_investment_config** — 用户问「配置」「止盈止损线」时调用
7. **get_snapshot_history** — 用户想看某基金的历史走势时调用
8. **get_operation_history** — 用户想看交易记录时调用
9. **execute_trade** — 用户明确要求买入/卖出时调用（必须先确认！）
10. **add_fund_quick** — 用户要添加新基金时调用
11. **update_fund** — 用户描述某基金最新情况或要求修改数据时调用（如「把xx市值改成5200」「xx代码改成005827」「xx止盈线设为25%」），只传要改的字段，更新后汇报变化
12. **get_health_score** — 用户问「健康度」「评分」时调用
13. **get_trading_status** — 用户问「今天能交易吗」「什么时候收盘」时调用
14. **search_web** — 用户问最新新闻、政策、市场资讯时调用

**重要**：涉及持仓数据的问题，必须先调工具拿到最新数据再回答，禁止凭记忆编造数字。

**写操作区分**：新增基金用 add_fund_quick；买入/卖出用 execute_trade；修改已有基金的字段（市值/本金/代码/买入日期/止盈止损线/加仓档位等）用 update_fund，更新后如实汇报改了哪些字段。

## 回答格式
- 使用 Markdown 格式，表格、列表、加粗都可以用
- 金额保留两位小数，超过1万自动转「万」（如 ¥12.35万）
- 收益率用 +x.xx% 或 -x.xx% 格式，正数加 + 号
- 关键结论用 **加粗** 突出
- 给建议时要引用具体数据支撑，不要说空话

## 投资知识
- 中国公募基金交易时间为工作日 9:30-15:00
- 基金净值每个交易日晚上更新
- T日买入按T日净值确认，T+1确认份额
- 持有不足7天赎回费通常1.5%
- 止盈是锁定利润，止损是截断亏损，都是纪律不是情绪
- 定投/金字塔加仓是摊低成本的有效方法
- 不要把鸡蛋放一个篮子里，单只基金不超过总仓位的30-40%

## 安全边界
- 永远不要建议用户全仓买入或全仓卖出
- 交易前必须确认基金名称和金额
- 遇到用户极度焦虑时，建议冷静观察而非冲动操作
- 不推荐具体股票、不承诺收益、不预测涨跌
- 当用户有明显赌博心态时，温和提醒理性投资"""


@router.post("/chat/smart/stream")
async def chat_smart_stream(req: ChatRequest, user_id: str = Depends(_uid)):
    """智能对话（原生流式 SSE + Function Calling，逐 token 输出）"""
    if not settings.llm_configured:
        raise HTTPException(status_code=503, detail="服务端未配置 LLM API Key")

    # 保存用户消息
    conn = get_db()
    msg_id = gen_id()
    conn.execute(
        "INSERT INTO chat_messages (id, role, content, created_at, user_id) VALUES (?, ?, ?, ?, ?)",
        (msg_id, "user", req.message, now_str(), user_id),
    )
    conn.commit()
    conn.close()

    history_dicts = [{"role": m.role, "content": m.content} for m in req.history]

    async def event_stream():
        try:
            from app.agent._common import _get_client
            client = _get_client()

            messages = [
                {"role": "system", "content": SMART_CHAT_SYSTEM_PROMPT},
            ]
            if req.fund_context:
                messages.append({
                    "role": "system",
                    "content": f"用户当前持仓数据（仅供参考，需要精确数据请调用工具）：\n{req.fund_context}",
                })
            for msg in history_dicts[-20:]:
                messages.append(msg)
            messages.append({"role": "user", "content": req.message})

            full_reply = ""

            for _round in range(5):
                # === 原生流式调用 ===
                stream = client.chat.completions.create(
                    model=settings.LLM_MODEL,
                    messages=messages,
                    tools=TOOL_DEFINITIONS,
                    tool_choice="auto",
                    stream=True,
                    temperature=0.7,
                    max_tokens=2048,
                )

                # 累积流式结果
                content_chunks = []
                tool_call_chunks = {}  # {index: {"id":..., "name":..., "args":""}}

                for chunk in stream:
                    delta = chunk.choices[0].delta if chunk.choices else None
                    if not delta:
                        continue

                    # 普通文本内容 → 立即逐块输出
                    if delta.content:
                        content_chunks.append(delta.content)
                        full_reply += delta.content
                        yield f"data: {json.dumps({'content': delta.content}, ensure_ascii=False)}\n\n"

                    # 工具调用 → 累积（流式 API 下 tool_calls 分多个 chunk 到达）
                    if delta.tool_calls:
                        for tc in delta.tool_calls:
                            idx = tc.index
                            if idx not in tool_call_chunks:
                                tool_call_chunks[idx] = {"id": "", "name": "", "args": ""}
                            if tc.id:
                                tool_call_chunks[idx]["id"] = tc.id
                            if tc.function:
                                if tc.function.name:
                                    tool_call_chunks[idx]["name"] += tc.function.name
                                if tc.function.arguments:
                                    tool_call_chunks[idx]["args"] += tc.function.arguments

                # === 如果 AI 调用了工具 ===
                if tool_call_chunks:
                    # 构建 assistant 消息（含 tool_calls）
                    tool_calls_msg = []
                    for idx in sorted(tool_call_chunks.keys()):
                        tc = tool_call_chunks[idx]
                        tool_calls_msg.append({
                            "id": tc["id"],
                            "type": "function",
                            "function": {"name": tc["name"], "arguments": tc["args"]},
                        })

                    messages.append({
                        "role": "assistant",
                        "content": "".join(content_chunks) if content_chunks else None,
                        "tool_calls": tool_calls_msg,
                    })

                    for tc in tool_calls_msg:
                        tool_name = tc["function"]["name"]
                        try:
                            arguments = json.loads(tc["function"]["arguments"])
                        except json.JSONDecodeError:
                            arguments = {}

                        logger.info("Tool calling: %s(%s)", tool_name, arguments)
                        yield f"data: {json.dumps({'tool_call': tool_name, 'tool_args': arguments}, ensure_ascii=False)}\n\n"

                        result = execute_tool(tool_name, arguments, user_id)

                        yield f"data: {json.dumps({'tool_result': tool_name, 'content': result[:800] + ('...' if len(result) > 800 else '')}, ensure_ascii=False)}\n\n"

                        messages.append({
                            "role": "tool",
                            "tool_call_id": tc["id"],
                            "content": result,
                        })

                    full_reply = ""  # 工具调用轮不累积到最终回复
                    content_chunks = []
                    continue  # 下一轮让 AI 基于工具结果回复

                # === 没有工具调用，AI 已完整回复 ===
                break

            # 保存 AI 回复
            if full_reply:
                ai_id = gen_id()
                conn2 = get_db()
                conn2.execute(
                    "INSERT INTO chat_messages (id, role, content, created_at, user_id) VALUES (?, ?, ?, ?, ?)",
                    (ai_id, "assistant", full_reply, now_str(), user_id),
                )
                conn2.commit()
                conn2.close()

            yield f"data: {json.dumps({'content': '', 'done': True}, ensure_ascii=False)}\n\n"

        except Exception as e:
            logger.error("智能对话失败: %s", e, exc_info=True)
            yield f"data: {json.dumps({'error': str(e), 'done': True}, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


# ==================== 情绪文案 ====================

@router.post("/emotion", response_model=EmotionResponse)
async def emotion(req: EmotionRequest):
    """生成 AI 情绪文案"""
    if not settings.llm_configured:
        return EmotionResponse(
            title="💡 心情加油站",
            lines=["服务端未配置 LLM API Key，暂无法生成 AI 情绪段子"],
        )

    try:
        data = req.model_dump(by_alias=True)
        result = generate_emotion(
            fund_name=data["fundName"],
            today_change=data["todayChange"],
            total_return=data["totalReturn"],
            market_value=data["marketValue"],
        )
        return EmotionResponse(**result)
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))


@router.post("/emotion/stream")
async def emotion_stream(req: EmotionRequest):
    """生成 AI 情绪文案（流式 SSE）"""
    if not settings.llm_configured:
        raise HTTPException(status_code=503, detail="服务端未配置 LLM API Key")

    data = req.model_dump(by_alias=True)

    async def event_stream():
        import threading
        from queue import Queue as TQueue

        chunk_queue = TQueue()
        error_holder = []
        full_text = []

        def _run():
            try:
                for chunk in generate_emotion_stream(
                    fund_name=data["fundName"],
                    today_change=data["todayChange"],
                    total_return=data["totalReturn"],
                    market_value=data["marketValue"],
                ):
                    chunk_queue.put(chunk)
            except Exception as e:
                error_holder.append(e)
            finally:
                chunk_queue.put(None)

        thread = threading.Thread(target=_run, daemon=True)
        thread.start()

        logger.info("[SSE Emotion] 发送 connected")
        yield f"data: {json.dumps({'connected': True}, ensure_ascii=False)}\n\n"

        loop = asyncio.get_running_loop()
        while True:
            chunk = await loop.run_in_executor(None, chunk_queue.get)
            if chunk is None:
                break
            if chunk == '__REASONING__':
                yield f"data: {json.dumps({'reasoning': True}, ensure_ascii=False)}\n\n"
            else:
                full_text.append(chunk)
                yield f"data: {json.dumps({'content': chunk}, ensure_ascii=False)}\n\n"

        thread.join(timeout=5)

        if error_holder:
            logger.error("流式情绪文案生成失败: %s", error_holder[0])
            yield f"data: {json.dumps({'error': str(error_holder[0])}, ensure_ascii=False)}\n\n"
            return

        # 从完整文本解析 JSON
        raw = "".join(full_text).strip()
        import json as _json
        try:
            parsed = _json.loads(raw)
            result = {"title": parsed.get("title", ""), "lines": parsed.get("lines", [])}
        except (_json.JSONDecodeError, Exception):
            lines = [l.strip() for l in raw.split("\n") if l.strip()]
            result = {"title": lines[0][:15] if lines else "AI 情绪加油站", "lines": lines if lines else []}
        yield f"data: {_json.dumps({'done': True, 'result': result}, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no", "Connection": "keep-alive"},
    )


# ==================== AI 操作建议解读 ====================

@router.post("/advice/interpret", response_model=AdviceInterpretResponse)
async def interpret(req: AdviceInterpretRequest):
    """AI 解读规则引擎的操作建议"""
    if not settings.llm_configured:
        raise HTTPException(
            status_code=503,
            detail="服务端未配置 LLM API Key，请在 .env 文件中设置 LLM_API_KEY",
        )

    try:
        data = req.model_dump(by_alias=True)
        text = interpret_advice(
            fund_name=data["fundName"],
            fund_data=data["fundData"],
            rule_result=data["ruleResult"],
            warning=data.get("warning"),
            config_info=data.get("configInfo"),
        )
        return AdviceInterpretResponse(interpretation=text)
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))


@router.post("/advice/interpret/stream")
async def interpret_stream(req: AdviceInterpretRequest):
    """AI 解读规则引擎的操作建议（流式 SSE）"""
    if not settings.llm_configured:
        raise HTTPException(status_code=503, detail="服务端未配置 LLM API Key")

    data = req.model_dump(by_alias=True)

    async def event_stream():
        import threading
        from queue import Queue as TQueue

        chunk_queue = TQueue()
        error_holder = []

        def _run():
            try:
                for chunk in interpret_advice_stream(
                    fund_name=data["fundName"],
                    fund_data=data["fundData"],
                    rule_result=data["ruleResult"],
                    warning=data.get("warning"),
                    config_info=data.get("configInfo"),
                ):
                    chunk_queue.put(chunk)
            except Exception as e:
                error_holder.append(e)
            finally:
                chunk_queue.put(None)

        thread = threading.Thread(target=_run, daemon=True)
        thread.start()

        logger.info("[SSE AdviceInterpret] 发送 connected")
        yield f"data: {json.dumps({'connected': True}, ensure_ascii=False)}\n\n"

        loop = asyncio.get_running_loop()
        while True:
            chunk = await loop.run_in_executor(None, chunk_queue.get)
            if chunk is None:
                break
            if chunk == '__REASONING__':
                yield f"data: {json.dumps({'reasoning': True}, ensure_ascii=False)}\n\n"
            else:
                yield f"data: {json.dumps({'content': chunk}, ensure_ascii=False)}\n\n"

        thread.join(timeout=5)

        if error_holder:
            logger.error("流式解读建议失败: %s", error_holder[0])
            yield f"data: {json.dumps({'error': str(error_holder[0])}, ensure_ascii=False)}\n\n"
            return

        yield f"data: {json.dumps({'done': True}, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no", "Connection": "keep-alive"},
    )
