"""操作历史路由"""

import logging
from typing import List, Optional

from fastapi import APIRouter, HTTPException

from app.database import get_db, gen_id, now_str, today_str
from app.models import HistoryCreate, HistoryOut, HistoryEvaluateResponse

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/history", tags=["操作历史"])


@router.get("", response_model=List[HistoryOut])
async def list_history(fund_name: Optional[str] = None):
    """获取操作历史（可按基金名筛选）"""
    conn = get_db()
    if fund_name:
        rows = conn.execute(
            "SELECT * FROM history WHERE fund_name = ? ORDER BY created_at DESC",
            (fund_name,),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM history ORDER BY created_at DESC"
        ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


@router.post("", response_model=HistoryOut)
async def create_history(item: HistoryCreate):
    """添加操作记录"""
    conn = get_db()
    hid = gen_id()
    data = item.model_dump(by_alias=True)
    conn.execute(
        """INSERT INTO history
           (id, date, fund_name, type, amount, return_rate, note, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            hid,
            data.get("date") or today_str(),
            data["fundName"],
            data["type"],
            data["amount"],
            data["returnRate"],
            data["note"],
            now_str(),
        ),
    )
    conn.commit()
    row = conn.execute("SELECT * FROM history WHERE id = ?", (hid,)).fetchone()
    conn.close()
    return dict(row)


@router.delete("")
async def clear_history():
    """清空所有操作历史"""
    conn = get_db()
    conn.execute("DELETE FROM history")
    conn.commit()
    conn.close()
    return {"ok": True}


@router.post("/evaluate/{history_id}", response_model=HistoryEvaluateResponse)
async def evaluate_history(history_id: str):
    """对指定操作历史记录进行 AI 评价，结果保存到数据库"""
    conn = get_db()
    try:
        row = conn.execute(
            "SELECT * FROM history WHERE id = ?", (history_id,)
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
