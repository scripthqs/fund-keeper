"""截图同步路由 - AI 识图 + 更新基金持仓数据"""

import json
import logging
from typing import List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.agent import parse_screenshot_for_sync
from app.config import settings
from app.database import get_db, gen_id, now_str, today_str

router = APIRouter(prefix="/api", tags=["截图同步"])
logger = logging.getLogger(__name__)


# ==================== 请求/响应模型 ====================

class ScreenshotSyncRequest(BaseModel):
    """截图同步请求"""
    image: str  # base64 data URL
    funds: List[dict] = Field(default_factory=list)  # 现有基金列表


class FundChangeItem(BaseModel):
    """单个基金变更项"""
    fundId: str = ""
    fundName: str = ""
    matched: bool = True
    oldData: dict = Field(default_factory=dict)
    newData: dict = Field(default_factory=dict)
    changes: List[str] = Field(default_factory=list)


class NewFundItem(BaseModel):
    """新基金"""
    name: str = ""
    currentMarketValue: float = 0
    currentReturnRate: float = 0
    todayChange: float = 0
    totalBuyAmount: float = 0
    initialPrincipal: float = 0
    buyDate: str = ""


class UnchangedItem(BaseModel):
    """未变化的基金"""
    fundId: str = ""
    fundName: str = ""


class ScreenshotSyncResponse(BaseModel):
    """截图同步结果（预览，未实际更新）"""
    matches: List[FundChangeItem] = Field(default_factory=list)
    newFunds: List[NewFundItem] = Field(default_factory=list)
    unchanged: List[UnchangedItem] = Field(default_factory=list)
    error: str = ""


class ApplySyncRequest(BaseModel):
    """确认同步请求"""
    # 确认要修改的基金变更（fundId + newData）
    applyMatches: List[dict] = Field(default_factory=list)
    # 确认要新增的基金
    applyNewFunds: List[dict] = Field(default_factory=list)


class ApplySyncResponse(BaseModel):
    """同步执行结果"""
    updated: List[str] = Field(default_factory=list)  # 已更新的基金名
    created: List[str] = Field(default_factory=list)  # 已新增的基金名
    ok: bool = True


# ==================== 端点 ====================

@router.post("/screenshot-sync", response_model=ScreenshotSyncResponse)
async def screenshot_sync(req: ScreenshotSyncRequest):
    """
    上传基金持仓截图，AI 识别后返回变更预览。
    此端点不会实际修改数据库，仅返回识别和对比结果。
    """
    if not settings.llm_configured:
        raise HTTPException(
            status_code=503,
            detail="服务端未配置 LLM API Key，请在 .env 文件中设置 LLM_API_KEY",
        )

    if not req.image:
        raise HTTPException(status_code=400, detail="请提供截图数据")

    try:
        result = parse_screenshot_for_sync(
            image_base64=req.image,
            existing_funds=req.funds,
        )
        return ScreenshotSyncResponse(
            matches=[FundChangeItem(**m) for m in result.get("matches", [])],
            newFunds=[NewFundItem(**n) for n in result.get("newFunds", [])],
            unchanged=[UnchangedItem(**u) for u in result.get("unchanged", [])],
            error=result.get("error", ""),
        )
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        logger.error("截图同步失败: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/screenshot-sync/apply", response_model=ApplySyncResponse)
async def screenshot_sync_apply(req: ApplySyncRequest):
    """
    确认执行截图同步：根据用户确认的变更数据，实际更新/新增数据库中的基金记录。
    """
    conn = get_db()
    updated = []
    created = []

    try:
        # 1. 处理修改：更新已有基金
        for item in req.applyMatches:
            fund_id = item.get("fundId", "")
            if not fund_id:
                continue

            existing = conn.execute(
                "SELECT * FROM funds WHERE id = ?", (fund_id,)
            ).fetchone()
            if not existing:
                continue

            existing = dict(existing)
            nd = item.get("newData", {})

            # 合并数据：用新数据覆盖旧数据，保留未提供的字段
            new_name = nd.get("name") or existing["name"]
            new_market_value = nd.get("currentMarketValue", existing["current_market_value"])
            new_return_rate = nd.get("currentReturnRate", existing["current_return_rate"])
            new_buy_amount = nd.get("totalBuyAmount") or existing["total_buy_amount"]
            new_principal = nd.get("initialPrincipal") or existing["initial_principal"]
            new_buy_date = nd.get("buyDate") or existing["buy_date"]

            conn.execute(
                """UPDATE funds SET
                   name=?, initial_principal=?, buy_date=?, total_buy_amount=?,
                   current_market_value=?, current_return_rate=?
                   WHERE id=?""",
                (
                    new_name,
                    new_principal,
                    new_buy_date,
                    new_buy_amount,
                    new_market_value,
                    new_return_rate,
                    fund_id,
                ),
            )
            updated.append(new_name)

        # 2. 处理新增基金
        for item in req.applyNewFunds:
            fund_id = gen_id()
            name = item.get("name", "新基金")
            market_value = item.get("currentMarketValue", 0)
            return_rate = item.get("currentReturnRate", 0)
            buy_amount = item.get("totalBuyAmount", 0)
            principal = item.get("initialPrincipal", market_value)
            buy_date = item.get("buyDate", "")

            conn.execute(
                """INSERT INTO funds
                   (id, name, initial_principal, buy_date, total_buy_amount,
                    total_sell_amount, current_market_value, current_return_rate, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    fund_id,
                    name,
                    principal,
                    buy_date,
                    buy_amount,
                    0,  # total_sell_amount
                    market_value,
                    return_rate,
                    now_str(),
                ),
            )
            created.append(name)

        conn.commit()

        # 3. 为变更的基金记录操作历史
        for name in updated:
            history_id = gen_id()
            conn.execute(
                """INSERT INTO history (id, date, fund_name, type, amount, return_rate, note, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    history_id,
                    today_str(),
                    name,
                    "更新",
                    0,
                    0,
                    "截图同步更新持仓数据",
                    now_str(),
                ),
            )

        conn.commit()

        return ApplySyncResponse(updated=updated, created=created, ok=True)

    except Exception as e:
        conn.rollback()
        logger.error("截图同步执行失败: %s", e)
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()
