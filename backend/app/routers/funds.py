"""基金 CRUD 路由 + 天天基金自动更新"""

import json
import logging
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query

from app.database import get_db, gen_id, now_str, today_str
from app.models import (
    FundCreate, FundOut, FundUpdate, ExecuteActionRequest, ExecuteActionResponse,
    FundQueryResponse, AutoUpdateResult, AutoUpdateResponse, AddTier,
    TierRecommendRequest, TierRecommendResponse,
)

from app.fund_api import query_fund_by_code, get_fund_nav_on_date, FundQueryError

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/funds", tags=["基金管理"])


@router.get("")
async def list_funds():
    """获取所有基金"""
    conn = get_db()
    rows = conn.execute("SELECT * FROM funds ORDER BY created_at").fetchall()
    conn.close()
    result = []
    for r in rows:
        d = dict(r)
        # 反序列化 add_tiers JSON
        try:
            d["add_tiers"] = json.loads(d.get("add_tiers", "")) if d.get("add_tiers") else []
        except (json.JSONDecodeError, TypeError):
            d["add_tiers"] = []
        item = FundOut(**d).model_dump(by_alias=True)
        result.append(item)
    return result


@router.post("")
async def create_fund(fund: FundCreate):
    """添加基金"""
    conn = get_db()
    fund_id = gen_id()
    data = fund.model_dump(by_alias=True)
    # 直接从 Pydantic 模型取出 add_tiers，确保拿到正确数据
    tiers_raw = fund.add_tiers or []
    add_tiers_json = json.dumps([t.model_dump() for t in tiers_raw], ensure_ascii=False)
    conn.execute(
        """INSERT INTO funds
           (id, name, fund_code, fund_shares, initial_principal, buy_date,
            total_buy_amount, total_sell_amount, current_market_value,
            current_return_rate, max_investment, add_tiers,
            stop_profit_line, stop_loss_line, stop_profit_ratio, stop_loss_ratio,
            created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
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
            data.get("maxInvestment", 0),
            add_tiers_json,
            data.get("stopProfitLine", 0),
            data.get("stopLossLine", 0),
            data.get("stopProfitRatio", 0),
            data.get("stopLossRatio", 0),
            now_str(),
        ),
    )
    conn.commit()
    row = conn.execute("SELECT * FROM funds WHERE id = ?", (fund_id,)).fetchone()
    d = dict(row)
    try:
        d["add_tiers"] = json.loads(d.get("add_tiers", "")) if d.get("add_tiers") else []
    except (json.JSONDecodeError, TypeError):
        d["add_tiers"] = []
    conn.close()
    return FundOut(**d).model_dump(by_alias=True)


@router.put("/{fund_id}")
async def update_fund(fund_id: str, fund: FundUpdate):
    """编辑基金"""
    conn = get_db()
    existing = conn.execute("SELECT id FROM funds WHERE id = ?", (fund_id,)).fetchone()
    if not existing:
        conn.close()
        raise HTTPException(status_code=404, detail="基金不存在")

    data = fund.model_dump(by_alias=True)
    # 直接从 Pydantic 模型取出 add_tiers，确保拿到正确数据
    tiers_raw = fund.add_tiers or []
    add_tiers_json = json.dumps([t.model_dump() for t in tiers_raw], ensure_ascii=False)
    conn.execute(
        """UPDATE funds SET
           name=?, fund_code=?, fund_shares=?, initial_principal=?, buy_date=?,
           total_buy_amount=?, total_sell_amount=?, current_market_value=?,
           current_return_rate=?, max_investment=?, add_tiers=?,
           stop_profit_line=?, stop_loss_line=?, stop_profit_ratio=?, stop_loss_ratio=?
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
            data.get("maxInvestment", 0),
            add_tiers_json,
            data.get("stopProfitLine", 0),
            data.get("stopLossLine", 0),
            data.get("stopProfitRatio", 0),
            data.get("stopLossRatio", 0),
            fund_id,
        ),
    )
    conn.commit()
    row = conn.execute("SELECT * FROM funds WHERE id = ?", (fund_id,)).fetchone()
    d = dict(row)
    try:
        d["add_tiers"] = json.loads(d.get("add_tiers", "")) if d.get("add_tiers") else []
    except (json.JSONDecodeError, TypeError):
        d["add_tiers"] = []
    conn.close()
    return FundOut(**d).model_dump(by_alias=True)


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

    # 记录撤回快照（操作前状态）写入 history 表
    import json
    snapshot_before = json.dumps({
        "total_buy_amount": fund["total_buy_amount"],
        "total_sell_amount": fund["total_sell_amount"],
        "current_market_value": fund["current_market_value"],
        "current_return_rate": fund["current_return_rate"],
    }, ensure_ascii=False)

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
        """INSERT INTO history (id, date, fund_name, type, amount, return_rate, note, created_at, snapshot_before)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            history_id,
            today_str(),
            updated["name"],
            action_type,
            req.amount,
            updated["current_return_rate"],
            note,
            now_str(),
            snapshot_before,
        ),
    )

    conn.commit()
    result = dict(updated)
    conn.close()
    return {"ok": True, "fund": result, "historyId": history_id}


@router.post("/undo/{history_id}")
async def undo_action(history_id: str):
    """撤回指定操作记录，恢复基金到操作前状态"""
    conn = get_db()
    row = conn.execute("SELECT * FROM history WHERE id = ?", (history_id,)).fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="操作记录不存在")
    row = dict(row)

    snapshot = row.get("snapshot_before")
    if not snapshot:
        conn.close()
        raise HTTPException(status_code=400, detail="该操作记录没有撤回快照（可能为旧数据）")

    import json
    try:
        before = json.loads(snapshot)
    except json.JSONDecodeError:
        conn.close()
        raise HTTPException(status_code=500, detail="撤回快照数据损坏")

    fund_name = row["fund_name"]
    fund = conn.execute("SELECT * FROM funds WHERE name = ?", (fund_name,)).fetchone()
    if not fund:
        conn.close()
        raise HTTPException(status_code=404, detail="对应基金不存在，可能已被删除")

    fund = dict(fund)
    conn.execute(
        """UPDATE funds SET total_buy_amount=?, total_sell_amount=?,
           current_market_value=?, current_return_rate=? WHERE name=?""",
        (
            before["total_buy_amount"],
            before["total_sell_amount"],
            before["current_market_value"],
            before["current_return_rate"],
            fund_name,
        ),
    )
    # 删除该条历史记录
    conn.execute("DELETE FROM history WHERE id = ?", (history_id,))
    conn.commit()

    updated = conn.execute("SELECT * FROM funds WHERE name = ?", (fund_name,)).fetchone()
    result = dict(updated)
    conn.close()
    return {"ok": True, "fund": result}


# ==================== AI 智能推荐加仓档位 ====================

@router.post("/ai-recommend-tiers")
async def ai_recommend_tiers(req: "TierRecommendRequest"):
    """AI 根据基金的初始本金、投入上限、当前收益 + 宏观政策分析，生成合理的金字塔加仓档位"""
    from app.config import settings
    if not settings.llm_configured:
        raise HTTPException(status_code=503, detail="服务端未配置 LLM API Key")

    from app.agent import recommend_add_tiers, analyze_fund_macro
    try:
        data = req.model_dump(by_alias=True)

        # 第一步：宏观政策分析
        fund_name = data["fundName"]
        macro = analyze_fund_macro(fund_name)
        if macro.get("error"):
            logger.warning("宏观分析失败：%s", macro.get("message"))
            # 宏观分析失败不阻塞档位推荐，把错误信息带给前端展示
            result = recommend_add_tiers(
                fund_name=data["fundName"],
                total_buy_amount=data["totalBuyAmount"],
                initial_principal=data["initialPrincipal"],
                max_investment=data["maxInvestment"],
                current_return_rate=data["currentReturnRate"],
                current_market_value=data["currentMarketValue"],
                hold_days=data.get("holdDays", 0),
                macro_analysis=None,
            )
            result["macroAnalysis"] = macro
            return result
        else:
            logger.info("宏观分析完成: %s -> 行业=%s 政策评分=%d 调整系数=%.2f",
                        fund_name, macro.get("sector"), macro.get("policyScore"),
                        macro.get("aggressiveness", 0))

        # 第二步：结合宏观分析推荐策略
        result = recommend_add_tiers(
            fund_name=data["fundName"],
            total_buy_amount=data["totalBuyAmount"],
            initial_principal=data["initialPrincipal"],
            max_investment=data["maxInvestment"],
            current_return_rate=data["currentReturnRate"],
            current_market_value=data["currentMarketValue"],
            hold_days=data.get("holdDays", 0),
            macro_analysis=macro,
        )

        # 合并宏观分析结果到响应
        result["macroAnalysis"] = {
            "sector": macro.get("sector", ""),
            "policyScore": macro.get("policyScore", 50),
            "keyPolicies": macro.get("keyPolicies", []),
            "trend": macro.get("trend", ""),
            "aggressiveness": macro.get("aggressiveness", 0),
            "analysis": macro.get("analysis", ""),
        }

        return result
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
