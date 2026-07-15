"""基金 CRUD 路由"""

from typing import List, Optional

from fastapi import APIRouter, HTTPException

from app.database import get_db, gen_id, now_str
from app.models import FundCreate, FundOut, FundUpdate, ExecuteActionRequest

router = APIRouter(prefix="/api/funds", tags=["基金管理"])


@router.get("", response_model=List[FundOut])
async def list_funds():
    """获取所有基金"""
    conn = get_db()
    rows = conn.execute("SELECT * FROM funds ORDER BY created_at").fetchall()
    conn.close()
    return [dict(r) for r in rows]


@router.post("", response_model=FundOut)
async def create_fund(fund: FundCreate):
    """添加基金"""
    conn = get_db()
    fund_id = gen_id()
    data = fund.model_dump(by_alias=True)
    conn.execute(
        """INSERT INTO funds
           (id, name, initial_principal, buy_date, total_buy_amount,
            total_sell_amount, current_market_value, current_return_rate, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            fund_id,
            data["name"],
            data["initialPrincipal"],
            data["buyDate"],
            data["totalBuyAmount"],
            data["totalSellAmount"],
            data["currentMarketValue"],
            data["currentReturnRate"],
            now_str(),
        ),
    )
    conn.commit()
    row = conn.execute("SELECT * FROM funds WHERE id = ?", (fund_id,)).fetchone()
    conn.close()
    return dict(row)


@router.put("/{fund_id}", response_model=FundOut)
async def update_fund(fund_id: str, fund: FundUpdate):
    """编辑基金"""
    conn = get_db()
    existing = conn.execute("SELECT id FROM funds WHERE id = ?", (fund_id,)).fetchone()
    if not existing:
        conn.close()
        raise HTTPException(status_code=404, detail="基金不存在")

    data = fund.model_dump(by_alias=True)
    conn.execute(
        """UPDATE funds SET
           name=?, initial_principal=?, buy_date=?, total_buy_amount=?,
           total_sell_amount=?, current_market_value=?, current_return_rate=?
           WHERE id=?""",
        (
            data["name"],
            data["initialPrincipal"],
            data["buyDate"],
            data["totalBuyAmount"],
            data["totalSellAmount"],
            data["currentMarketValue"],
            data["currentReturnRate"],
            fund_id,
        ),
    )
    conn.commit()
    row = conn.execute("SELECT * FROM funds WHERE id = ?", (fund_id,)).fetchone()
    conn.close()
    return dict(row)


@router.delete("/{fund_id}")
async def delete_fund(fund_id: str):
    """删除基金"""
    conn = get_db()
    conn.execute("DELETE FROM funds WHERE id = ?", (fund_id,))
    conn.commit()
    conn.close()
    return {"ok": True}


@router.post("/action")
async def execute_action(req: ExecuteActionRequest):
    """执行买入/卖出操作，更新基金数据并记录历史"""
    conn = get_db()
    fund = conn.execute(
        "SELECT * FROM funds WHERE id = ?", (req.fund_id,)
    ).fetchone()
    if not fund:
        conn.close()
        raise HTTPException(status_code=404, detail="基金不存在")

    fund = dict(fund)
    action_type = req.action_type

    if action_type == "买入":
        new_buy = fund["total_buy_amount"] + req.amount
        new_market = fund["current_market_value"] + req.amount
        conn.execute(
            "UPDATE funds SET total_buy_amount=?, current_market_value=? WHERE id=?",
            (new_buy, new_market, req.fund_id),
        )
    elif action_type == "卖出":
        new_sell = fund["total_sell_amount"] + req.amount
        new_market = max(0, fund["current_market_value"] - req.amount)
        conn.execute(
            "UPDATE funds SET total_sell_amount=?, current_market_value=? WHERE id=?",
            (new_sell, new_market, req.fund_id),
        )

    # 重新计算收益率
    updated = conn.execute(
        "SELECT * FROM funds WHERE id = ?", (req.fund_id,)
    ).fetchone()
    updated = dict(updated)
    if updated["total_buy_amount"] > 0:
        new_rate = (
            (updated["current_market_value"] - updated["total_buy_amount"] + updated["total_sell_amount"])
            / updated["total_buy_amount"]
        ) * 100
        conn.execute(
            "UPDATE funds SET current_return_rate=? WHERE id=?",
            (new_rate, req.fund_id),
        )
        updated["current_return_rate"] = new_rate

    # 记录历史
    if req.note:
        note = req.note
    else:
        reason_map = {
            "sell": "触发止盈",
            "buy": "触发加仓",
            "stop_loss": "触发止损",
            "trailing_sell": "移动止盈",
        }
        note = reason_map.get(req.reason_type, "")
        if req.is_max:
            note += "（上限）"

    from app.database import today_str
    history_id = gen_id()
    conn.execute(
        """INSERT INTO history (id, date, fund_name, type, amount, return_rate, note, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            history_id,
            today_str(),
            updated["name"],
            action_type,
            req.amount,
            updated["current_return_rate"],
            note,
            now_str(),
        ),
    )

    conn.commit()
    result = dict(updated)
    conn.close()
    return {"ok": True, "fund": result}
