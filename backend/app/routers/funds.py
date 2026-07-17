"""基金 CRUD 路由 + 天天基金自动更新"""

import logging
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query

from app.database import get_db, gen_id, now_str, today_str
from app.models import (
    FundCreate, FundOut, FundUpdate, ExecuteActionRequest, ExecuteActionResponse,
    FundQueryResponse, AutoUpdateResult, AutoUpdateResponse,
)

from app.fund_api import query_fund_by_code, get_fund_nav_on_date, FundQueryError

logger = logging.getLogger(__name__)
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
           (id, name, fund_code, fund_shares, initial_principal, buy_date,
            total_buy_amount, total_sell_amount, current_market_value,
            current_return_rate, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            fund_id,
            data["name"],
            data.get("fundCode", ""),
            data.get("fundShares", 0),
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
           name=?, fund_code=?, fund_shares=?, initial_principal=?, buy_date=?,
           total_buy_amount=?, total_sell_amount=?, current_market_value=?,
           current_return_rate=?
           WHERE id=?""",
        (
            data["name"],
            data.get("fundCode", ""),
            data.get("fundShares", 0),
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


# ==================== 天天基金接口 ====================

@router.get("/query-fund", response_model=Optional[FundQueryResponse])
async def query_fund(code: str = Query(..., min_length=6, max_length=6, description="基金代码")):
    """
    通过基金代码查询天天基金实时数据
    返回基金名称、最新净值、实时估值、估算涨跌幅
    """
    try:
        info = await query_fund_by_code(code)
        return info
    except FundQueryError as e:
        # 根据错误类型返回不同状态码
        status_code = 502 if e.recoverable else 404
        raise HTTPException(
            status_code=status_code,
            detail=e.args[0] if e.args else "查询失败",
        ) from e


@router.post("/auto-update", response_model=AutoUpdateResponse)
async def auto_update_nav():
    """
    一键获取所有基金最新净值/涨跌幅（预览模式）
    从天天基金拉取最新数据并计算预期市值，不直接写入数据库，
    由前端展示确认后手动应用
    """
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM funds WHERE fund_code != '' AND fund_code IS NOT NULL"
    ).fetchall()
    conn.close()

    results: list[AutoUpdateResult] = []
    updated_count = 0
    failed_count = 0
    skipped_count = 0

    for row in rows:
        fund = dict(row)
        code = fund.get("fund_code", "").strip()
        if not code:
            skipped_count += 1
            continue

        try:
            info = await query_fund_by_code(code)
        except FundQueryError:
            results.append(AutoUpdateResult(
                fundId=fund["id"],
                fundName=fund["name"],
                fundCode=code,
                success=False,
                oldMarketValue=fund["current_market_value"],
                newMarketValue=fund["current_market_value"],
                message="获取基金实时数据失败",
            ))
            failed_count += 1
            continue

        if info["nav"] <= 0:
            results.append(AutoUpdateResult(
                fundId=fund["id"],
                fundName=fund["name"],
                fundCode=code,
                success=False,
                oldMarketValue=fund["current_market_value"],
                newMarketValue=fund["current_market_value"],
                message="获取基金实时数据失败",
            ))
            failed_count += 1
            continue

        old_market = fund["current_market_value"]
        shares = fund.get("fund_shares", 0) or 0
        today_change = info.get("estimated_change")

        if shares > 0:
            new_market = round(shares * info["nav"], 2)
            message = f"净值 {info['nav']}，份额 {shares}"
        elif today_change is not None and old_market > 0:
            new_market = round(old_market * (1 + today_change / 100), 2)
            message = f"今日估算涨跌幅 {today_change:+.2f}%"
        else:
            results.append(AutoUpdateResult(
                fundId=fund["id"],
                fundName=fund["name"],
                fundCode=code,
                success=False,
                oldMarketValue=old_market,
                newMarketValue=old_market,
                message="缺少份额数据且无法获取涨跌幅，请先填写基金份额",
            ))
            failed_count += 1
            continue

        # 计算预期收益率（不写数据库）
        total_buy = fund.get("total_buy_amount", 0) or 0
        total_sell = fund.get("total_sell_amount", 0) or 0
        if total_buy > 0:
            new_return_rate = round(
                (new_market - total_buy + total_sell) / total_buy * 100, 4
            )
        else:
            new_return_rate = fund.get("current_return_rate", 0) or 0

        # 计算今日收益
        today_profit = round(new_market - old_market, 2)

        results.append(AutoUpdateResult(
            fundId=fund["id"],
            fundName=fund["name"],
            fundCode=code,
            success=True,
            oldMarketValue=old_market,
            newMarketValue=new_market,
            todayChange=today_change,
            todayProfit=today_profit,
            calculatedReturnRate=new_return_rate,
            message=message,
        ))
        updated_count += 1

    return AutoUpdateResponse(
        updatedCount=updated_count,
        failedCount=failed_count,
        skippedCount=skipped_count,
        results=results,
    )


@router.post("/action", response_model=ExecuteActionResponse)
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
