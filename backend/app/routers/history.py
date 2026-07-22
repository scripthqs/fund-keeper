"""操作历史路由"""

import asyncio
import json
import logging
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Depends, Header
from fastapi.responses import StreamingResponse

from app.database import get_db, gen_id, now_str, today_str, get_current_user_id
from app.models import HistoryCreate, HistoryOut, HistoryEvaluateResponse

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/history", tags=["操作历史"])


async def _uid(x_username: str = Header(None, alias="X-Username")):
    return get_current_user_id(x_username)


@router.get("", response_model=List[HistoryOut])
async def list_history(fund_name: Optional[str] = None, user_id: str = Depends(_uid)):
    """获取操作历史（可按基金名筛选）"""
    conn = get_db()
    if fund_name:
        rows = conn.execute(
            "SELECT * FROM history WHERE fund_name = ? AND user_id = ? ORDER BY created_at DESC",
            (fund_name, user_id),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM history WHERE user_id = ? ORDER BY created_at DESC",
            (user_id,),
        ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


@router.post("", response_model=HistoryOut)
async def create_history(item: HistoryCreate, user_id: str = Depends(_uid)):
    """添加操作记录"""
    conn = get_db()
    hid = gen_id()
    data = item.model_dump(by_alias=True)
    conn.execute(
        """INSERT INTO history
           (id, date, fund_name, type, amount, return_rate, note, created_at, user_id)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            hid,
            data.get("date") or today_str(),
            data["fundName"],
            data["type"],
            data["amount"],
            data["returnRate"],
            data["note"],
            now_str(),
            user_id,
        ),
    )
    conn.commit()
    row = conn.execute("SELECT * FROM history WHERE id = ?", (hid,)).fetchone()
    conn.close()
    return dict(row)


@router.delete("")
async def clear_history(user_id: str = Depends(_uid)):
    """清空当前用户的所有操作历史"""
    conn = get_db()
    conn.execute("DELETE FROM history WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()
    return {"ok": True}


@router.post("/evaluate/{history_id}", response_model=HistoryEvaluateResponse)
async def evaluate_history(history_id: str, user_id: str = Depends(_uid)):
    """对指定操作历史记录进行 AI 评价，结果保存到数据库"""
    conn = get_db()
    try:
        row = conn.execute(
            "SELECT * FROM history WHERE id = ? AND user_id = ?", (history_id, user_id)
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="操作记录不存在")

        record = dict(row)

        # 如果已有评价，直接返回
        if record.get("ai_evaluation") and record["ai_evaluation"].strip():
            return {"evaluation": record["ai_evaluation"]}

        from app.agent import evaluate_operation

        evaluation = evaluate_operation(
            fund_name=record.get("fund_name", ""),
            action_type=record.get("type", ""),
            amount=record.get("amount", 0),
            return_rate=record.get("return_rate", 0),
            note=record.get("note", ""),
        )

        # 保存评价到数据库
        conn.execute(
            "UPDATE history SET ai_evaluation = ? WHERE id = ?",
            (evaluation, history_id),
        )
        conn.commit()

        return {"evaluation": evaluation}

    except HTTPException:
        raise
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        logger.error("AI 操作评价失败: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"评价失败: {str(e)}")
    finally:
        conn.close()


@router.post("/evaluate/stream/{history_id}")
async def evaluate_history_stream(history_id: str, user_id: str = Depends(_uid)):
    """对指定操作历史记录进行 AI 评价（流式 SSE），结果保存到数据库"""
    conn = get_db()
    row = conn.execute(
        "SELECT * FROM history WHERE id = ? AND user_id = ?", (history_id, user_id)
    ).fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="操作记录不存在")

    record = dict(row)

    # 如果已有评价，直接返回（不需要流式）
    if record.get("ai_evaluation") and record["ai_evaluation"].strip():
        conn.close()

        async def cached_stream():
            yield f"data: {json.dumps({'connected': True}, ensure_ascii=False)}\n\n"
            yield f"data: {json.dumps({'content': record['ai_evaluation']}, ensure_ascii=False)}\n\n"
            yield f"data: {json.dumps({'done': True}, ensure_ascii=False)}\n\n"

        return StreamingResponse(
            cached_stream(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no", "Connection": "keep-alive"},
        )

    conn.close()

    from app.agent import evaluate_operation_stream
    import threading
    from queue import Queue as TQueue
    from app.config import settings

    if not settings.llm_configured:
        raise HTTPException(status_code=503, detail="服务端未配置 LLM API Key")

    async def event_stream():
        chunk_queue = TQueue()
        error_holder = []
        full_text = []

        def _run():
            try:
                for chunk in evaluate_operation_stream(
                    fund_name=record.get("fund_name", ""),
                    action_type=record.get("type", ""),
                    amount=record.get("amount", 0),
                    return_rate=record.get("return_rate", 0),
                    note=record.get("note", ""),
                ):
                    chunk_queue.put(chunk)
            except Exception as e:
                error_holder.append(e)
            finally:
                chunk_queue.put(None)

        thread = threading.Thread(target=_run, daemon=True)
        thread.start()

        logger.info("[SSE EvaluateHistory] 发送 connected")
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
            logger.error("流式操作评价失败: %s", error_holder[0])
            yield f"data: {json.dumps({'error': str(error_holder[0])}, ensure_ascii=False)}\n\n"
            return

        evaluation = "".join(full_text).strip()

        # 保存评价到数据库
        conn2 = get_db()
        conn2.execute(
            "UPDATE history SET ai_evaluation = ? WHERE id = ?",
            (evaluation, history_id),
        )
        conn2.commit()
        conn2.close()

        yield f"data: {json.dumps({'done': True}, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no", "Connection": "keep-alive"},
    )
