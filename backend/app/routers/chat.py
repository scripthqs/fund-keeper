"""AI 聊天与情绪文案路由"""

import logging
from typing import List

from fastapi import APIRouter, HTTPException

from app.agent import chat_with_advisor, generate_emotion
from app.config import settings
from app.database import get_db, gen_id, now_str
from app.models import (
    ChatMessage,
    ChatRequest,
    ChatResponse,
    EmotionRequest,
    EmotionResponse,
)

router = APIRouter(prefix="/api", tags=["AI 对话"])
logger = logging.getLogger(__name__)


# ==================== 聊天消息管理 ====================

@router.get("/chat/messages", response_model=List[ChatMessage])
async def list_chat_messages():
    """获取所有聊天记录"""
    conn = get_db()
    rows = conn.execute(
        "SELECT role, content FROM chat_messages ORDER BY created_at"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


@router.delete("/chat/messages")
async def clear_chat_messages():
    """清空所有聊天记录"""
    conn = get_db()
    conn.execute("DELETE FROM chat_messages")
    conn.commit()
    conn.close()
    return {"ok": True}


# ==================== AI 对话 ====================

@router.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    """与 AI 投资顾问对话"""
    if not settings.llm_configured:
        raise HTTPException(
            status_code=503,
            detail="服务端未配置 LLM API Key，请在 .env 文件中设置 LLM_API_KEY",
        )

    # 保存用户消息
    conn = get_db()
    user_id = gen_id()
    conn.execute(
        "INSERT INTO chat_messages (id, role, content, created_at) VALUES (?, ?, ?, ?)",
        (user_id, "user", req.message, now_str()),
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
        "INSERT INTO chat_messages (id, role, content, created_at) VALUES (?, ?, ?, ?)",
        (ai_id, "assistant", reply, now_str()),
    )
    conn.commit()
    conn.close()

    return ChatResponse(reply=reply)


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
