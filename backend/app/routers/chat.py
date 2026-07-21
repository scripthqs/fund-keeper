"""AI 聊天与情绪文案路由"""

import asyncio
import json
import logging
from typing import List

from fastapi import APIRouter, HTTPException, Depends, Header
from fastapi.responses import StreamingResponse

from app.agent import chat_with_advisor, chat_with_advisor_stream, generate_emotion, interpret_advice
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
