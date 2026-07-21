"""每日快照路由"""

from typing import List

from fastapi import APIRouter, Depends, Header

from app.database import get_db, gen_id, today_str, get_current_user_id
from app.models import SnapshotCreate, SnapshotOut

router = APIRouter(prefix="/api/snapshots", tags=["每日快照"])


async def _uid(x_username: str = Header(None, alias="X-Username")):
    return get_current_user_id(x_username)


@router.get("/{fund_id}", response_model=List[SnapshotOut])
async def list_snapshots(fund_id: str, user_id: str = Depends(_uid)):
    """获取某基金的历史快照"""
    conn = get_db()
    rows = conn.execute(
        "SELECT fund_id, date, safety_cushion, recovery_needed, today_change, total_return "
        "FROM snapshots WHERE fund_id = ? AND user_id = ? ORDER BY date",
        (fund_id, user_id),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


@router.post("", response_model=SnapshotOut)
async def save_snapshot(snap: SnapshotCreate, user_id: str = Depends(_uid)):
    """保存每日快照（同一天覆盖）"""
    conn = get_db()
    data = snap.model_dump(by_alias=True)
    fund_id = data["fundId"]
    today = today_str()

    # 同一天只保留最新一条
    existing = conn.execute(
        "SELECT id FROM snapshots WHERE fund_id = ? AND date = ? AND user_id = ?",
        (fund_id, today, user_id),
    ).fetchone()

    if existing:
        conn.execute(
            """UPDATE snapshots SET
               safety_cushion=?, recovery_needed=?, today_change=?, total_return=?
               WHERE fund_id=? AND date=? AND user_id=?""",
            (
                data["safetyCushion"],
                data["recoveryNeeded"],
                data["todayChange"],
                data["totalReturn"],
                fund_id,
                today,
                user_id,
            ),
        )
    else:
        conn.execute(
            """INSERT INTO snapshots
               (id, fund_id, user_id, date, safety_cushion, recovery_needed, today_change, total_return)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                gen_id(),
                fund_id,
                user_id,
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
