"""每日快照路由"""

from typing import List

from fastapi import APIRouter

from app.database import get_db, gen_id, today_str
from app.models import SnapshotCreate, SnapshotOut

router = APIRouter(prefix="/api/snapshots", tags=["每日快照"])


@router.get("/{fund_id}", response_model=List[SnapshotOut])
async def list_snapshots(fund_id: str):
    """获取某基金的历史快照"""
    conn = get_db()
    rows = conn.execute(
        "SELECT fund_id, date, safety_cushion, recovery_needed, today_change, total_return "
        "FROM snapshots WHERE fund_id = ? ORDER BY date",
        (fund_id,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


@router.post("", response_model=SnapshotOut)
async def save_snapshot(snap: SnapshotCreate):
    """保存每日快照（同一天覆盖）"""
    conn = get_db()
    data = snap.model_dump(by_alias=True)
    fund_id = data["fundId"]
    today = today_str()

    # 同一天只保留最新一条
    existing = conn.execute(
        "SELECT id FROM snapshots WHERE fund_id = ? AND date = ?",
        (fund_id, today),
    ).fetchone()

    if existing:
        conn.execute(
            """UPDATE snapshots SET
               safety_cushion=?, recovery_needed=?, today_change=?, total_return=?
               WHERE fund_id=? AND date=?""",
            (
                data["safetyCushion"],
                data["recoveryNeeded"],
                data["todayChange"],
                data["totalReturn"],
                fund_id,
                today,
            ),
        )
    else:
        conn.execute(
            """INSERT INTO snapshots
               (id, fund_id, date, safety_cushion, recovery_needed, today_change, total_return)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                gen_id(),
                fund_id,
                today,
                data["safetyCushion"],
                data["recoveryNeeded"],
                data["todayChange"],
                data["totalReturn"],
            ),
        )

    conn.commit()
    conn.close()

    return {
        "fund_id": fund_id,
        "date": today,
        "safety_cushion": data["safetyCushion"],
        "recovery_needed": data["recoveryNeeded"],
        "today_change": data["todayChange"],
        "total_return": data["totalReturn"],
    }
