"""操作历史路由"""

from typing import List, Optional

from fastapi import APIRouter, HTTPException

from app.database import get_db, gen_id, now_str, today_str
from app.models import HistoryCreate, HistoryOut

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
