"""基金 CRUD 路由 + 基金数据自动更新"""

import asyncio
import json
import logging
from datetime import datetime, timedelta
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query, Depends, Header
from fastapi.responses import StreamingResponse

from app.database import get_db, gen_id, now_str, today_str, get_current_user_id
from app.models import (
    FundCreate, FundOut, FundUpdate, ExecuteActionRequest, ExecuteActionResponse,
    FundQueryResponse, AutoUpdateResult, AutoUpdateResponse, AddTier,
    TierRecommendRequest, TierRecommendResponse,
    OverallAnalysisRequest, OverallAnalysisResponse,
)

from app.fund_api import query_fund_by_code, get_fund_nav_on_date, FundQueryError, check_network_connectivity

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/funds", tags=["基金管理"])


async def _uid(x_username: str = Header(None, alias="X-Username")):
    return get_current_user_id(x_username)


def _parse_tiers(raw: str) -> list:
    """安全解析 JSON tiers 字符串"""
    if not raw:
        return []
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return []


@router.get("")
async def list_funds(user_id: str = Depends(_uid)):
    """获取当前用户的所有基金"""
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM funds WHERE user_id = ? ORDER BY created_at", (user_id,)
    ).fetchall()
    conn.close()
    result = []
    for r in rows:
        d = dict(r)
        # 反序列化 JSON 字段
        d["add_tiers"] = _parse_tiers(d.get("add_tiers", ""))
        d["pullback_tiers"] = _parse_tiers(d.get("pullback_tiers", ""))
        item = FundOut(**d).model_dump(by_alias=True)
        result.append(item)
    return result


@router.post("")
async def create_fund(fund: FundCreate, user_id: str = Depends(_uid)):
    """添加基金"""
    conn = get_db()
    fund_id = gen_id()
    data = fund.model_dump(by_alias=True)
    # 直接从 Pydantic 模型取出 add_tiers，确保拿到正确数据
    tiers_raw = fund.add_tiers or []
    add_tiers_json = json.dumps([t.model_dump() for t in tiers_raw], ensure_ascii=False)
    pullback_raw = fund.pullback_tiers or []
    pullback_tiers_json = json.dumps([t.model_dump() for t in pullback_raw], ensure_ascii=False)
    conn.execute(
        """INSERT INTO funds
           (id, name, fund_code, fund_shares, initial_principal, buy_date,
            total_buy_amount, total_sell_amount, current_market_value,
            current_return_rate, max_investment, add_tiers,
            strategy_type, pullback_tiers,
            stop_profit_line, stop_loss_line, stop_profit_ratio, stop_loss_ratio,
            created_at, user_id)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
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
            data.get("strategyType", "downside"),
            pullback_tiers_json,
            data.get("stopProfitLine", 0),
            data.get("stopLossLine", 0),
            data.get("stopProfitRatio", 0),
            data.get("stopLossRatio", 0),
            now_str(),
            user_id,
        ),
    )
    conn.commit()
    row = conn.execute(
        "SELECT * FROM funds WHERE id = ? AND user_id = ?", (fund_id, user_id)
    ).fetchone()
    d = dict(row)
    d["add_tiers"] = _parse_tiers(d.get("add_tiers", ""))
    d["pullback_tiers"] = _parse_tiers(d.get("pullback_tiers", ""))
    conn.close()
    return FundOut(**d).model_dump(by_alias=True)


@router.put("/{fund_id}")
async def update_fund(fund_id: str, fund: FundUpdate, user_id: str = Depends(_uid)):
    """编辑基金"""
    conn = get_db()
    existing = conn.execute(
        "SELECT id FROM funds WHERE id = ? AND user_id = ?", (fund_id, user_id)
    ).fetchone()
    if not existing:
        conn.close()
        raise HTTPException(status_code=404, detail="基金不存在")

    data = fund.model_dump(by_alias=True)
    # 直接从 Pydantic 模型取出 tiers，确保拿到正确数据
    tiers_raw = fund.add_tiers or []
    add_tiers_json = json.dumps([t.model_dump() for t in tiers_raw], ensure_ascii=False)
    pullback_raw = fund.pullback_tiers or []
    pullback_tiers_json = json.dumps([t.model_dump() for t in pullback_raw], ensure_ascii=False)
    conn.execute(
        """UPDATE funds SET
           name=?, fund_code=?, fund_shares=?, initial_principal=?, buy_date=?,
           total_buy_amount=?, total_sell_amount=?, current_market_value=?,
           current_return_rate=?, max_investment=?, add_tiers=?,
           strategy_type=?, pullback_tiers=?,
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
            data.get("strategyType", "downside"),
            pullback_tiers_json,
            data.get("stopProfitLine", 0),
            data.get("stopLossLine", 0),
            data.get("stopProfitRatio", 0),
            data.get("stopLossRatio", 0),
            fund_id,
        ),
    )
    conn.commit()
    row = conn.execute(
        "SELECT * FROM funds WHERE id = ? AND user_id = ?", (fund_id, user_id)
    ).fetchone()
    d = dict(row)
    d["add_tiers"] = _parse_tiers(d.get("add_tiers", ""))
    d["pullback_tiers"] = _parse_tiers(d.get("pullback_tiers", ""))
    conn.close()
    return FundOut(**d).model_dump(by_alias=True)


@router.delete("/{fund_id}")
async def delete_fund(fund_id: str, user_id: str = Depends(_uid)):
    """删除基金"""
    conn = get_db()
    conn.execute(
        "DELETE FROM funds WHERE id = ? AND user_id = ?", (fund_id, user_id)
    )
    conn.commit()
    conn.close()
    return {"ok": True}


# ==================== 基金查询接口 ====================

@router.get("/query-fund", response_model=Optional[FundQueryResponse])
async def query_fund(code: str = Query(..., min_length=6, max_length=6, description="基金代码")):
    """
    通过基金代码查询实时数据
    返回基金名称、最新净值、盘中实时估值（新浪财经）、估算涨跌幅
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
async def auto_update_nav(user_id: str = Depends(_uid)):
    """
    一键获取所有基金最新净值/涨跌幅（预览模式）
    从东方财富拉取最新净值、新浪财经获取盘中实时估值；
    盘中优先用新浪实时估值净值计算市值（实时反映涨跌），
    当晚净值结算后自动切回已结算净值。
    不直接写入数据库，由前端展示确认后手动应用
    """
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM funds WHERE fund_code != '' AND fund_code IS NOT NULL AND user_id = ?",
        (user_id,),
    ).fetchall()
    conn.close()

    async def _update_one(fund: dict) -> AutoUpdateResult:
        """处理单只基金的净值更新（用于并发执行）"""
        code = fund.get("fund_code", "").strip()
        if not code:
            return AutoUpdateResult(
                fundId=fund["id"], fundName=fund["name"], fundCode="",
                success=False, oldMarketValue=fund["current_market_value"],
                newMarketValue=fund["current_market_value"],
                message="缺少基金代码",
            )

        try:
            info = await query_fund_by_code(code)
        except FundQueryError:
            return AutoUpdateResult(
                fundId=fund["id"], fundName=fund["name"], fundCode=code,
                success=False,
                oldMarketValue=fund["current_market_value"],
                newMarketValue=fund["current_market_value"],
                message="获取基金实时数据失败",
            )

        # 选择用于计算市值的净值：
        # 盘中（已结算净值日期 < 北京今天）且新浪实时估值可用 → 用估值净值，实时反映涨跌；
        # 当晚净值已结算（date == 今天）或无估值 → 用准确的已结算净值。
        # 注意必须用北京时间判断"今天"，服务器在海外时本地日期可能差一天。
        beijing_today = (datetime.utcnow() + timedelta(hours=8)).strftime("%Y-%m-%d")
        settled_nav = info["nav"]
        est_nav = info.get("estimated_nav") or 0
        use_estimate = est_nav > 0 and info.get("date", "") < beijing_today
        nav_for_calc = est_nav if use_estimate else settled_nav
        nav_label = "实时估值" if use_estimate else "净值"

        if nav_for_calc <= 0:
            return AutoUpdateResult(
                fundId=fund["id"], fundName=fund["name"], fundCode=code,
                success=False,
                oldMarketValue=fund["current_market_value"],
                newMarketValue=fund["current_market_value"],
                message="获取基金实时数据失败",
            )

        old_market = fund["current_market_value"]
        shares = fund.get("fund_shares", 0) or 0

        # 今日涨跌幅：优先使用新浪实时估值涨跌幅
        today_change = info.get("estimated_change")

        if shares <= 0:
            # 无份额数据时仍视为成功，仅无法计算市值变化
            return AutoUpdateResult(
                fundId=fund["id"], fundName=fund["name"], fundCode=code,
                success=True,
                oldMarketValue=old_market, newMarketValue=old_market,
                todayChange=today_change, todayProfit=0,
                calculatedReturnRate=fund.get("current_return_rate", 0) or 0,
                message=f"{nav_label} {nav_for_calc}（缺少份额，无法计算市值变化）",
            )

        new_market = round(shares * nav_for_calc, 2)
        message = f"{nav_label} {nav_for_calc}，份额 {shares}"

        # 计算预期收益率（不写数据库）
        total_buy = fund.get("total_buy_amount", 0) or 0
        total_sell = fund.get("total_sell_amount", 0) or 0
        if total_buy > 0:
            new_return_rate = round(
                (new_market - total_buy + total_sell) / total_buy * 100, 4
            )
        else:
            new_return_rate = fund.get("current_return_rate", 0) or 0

        # 用历史净值反算涨跌幅（兜底）
        if today_change is None and nav_for_calc > 0 and old_market > 0:
            yesterday_nav = old_market / shares
            if yesterday_nav > 0:
                today_change = round((nav_for_calc - yesterday_nav) / yesterday_nav * 100, 4)
        today_profit = round(new_market - old_market, 2)

        return AutoUpdateResult(
            fundId=fund["id"], fundName=fund["name"], fundCode=code,
            success=True,
            oldMarketValue=old_market, newMarketValue=new_market,
            todayChange=today_change, todayProfit=today_profit,
            calculatedReturnRate=new_return_rate, message=message,
        )

    # 并发查询所有基金（带超时兜底：单只最长 40s，整体 60s）
    tasks = [asyncio.wait_for(_update_one(dict(row)), timeout=40) for row in rows]
    gathered = await asyncio.gather(*tasks, return_exceptions=True)

    results: list[AutoUpdateResult] = []
    updated_count = 0
    failed_count = 0
    skipped_count = 0

    for item in gathered:
        if isinstance(item, Exception):
            # 整体超时或其他异常时，记录为未知失败
            skipped_count += 1
            continue
        result: AutoUpdateResult = item
        results.append(result)
        if result.success:
            updated_count += 1
        else:
            failed_count += 1

    return AutoUpdateResponse(
        updatedCount=updated_count,
        failedCount=failed_count,
        skippedCount=skipped_count,
        results=results,
    )


@router.get("/network-check")
async def network_check():
    """诊断外部 API 网络连通性（排查海外/云平台部署时外网不通问题）"""
    try:
        result = await check_network_connectivity()
        return result
    except Exception as e:
        logger.error("网络诊断执行失败: %s", e)
        raise HTTPException(status_code=500, detail=f"诊断失败: {e}")


@router.post("/action", response_model=ExecuteActionResponse)
async def execute_action(req: ExecuteActionRequest, user_id: str = Depends(_uid)):
    """执行买入/卖出操作，更新基金数据并记录历史"""
    conn = get_db()
    try:
        fund = conn.execute(
            "SELECT * FROM funds WHERE id = ? AND user_id = ?", (req.fund_id, user_id)
        ).fetchone()
        if not fund:
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
        else:
            raise HTTPException(status_code=400, detail=f"不支持的操作类型: {action_type}")

        # 重新计算收益率
        updated = conn.execute(
            "SELECT * FROM funds WHERE id = ? AND user_id = ?", (req.fund_id, user_id)
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

        history_id = gen_id()
        conn.execute(
            """INSERT INTO history (id, date, fund_name, type, amount, return_rate, note, created_at, snapshot_before, user_id)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                history_id,
                today_str(),
                updated["name"],
                action_type,
                req.amount,
                fund["current_return_rate"],
                note,
                now_str(),
                snapshot_before,
                user_id,
            ),
        )

        conn.commit()

        # 反序列化 JSON 字段（与 list_funds 保持一致）
        result = dict(updated)
        result["add_tiers"] = _parse_tiers(result.get("add_tiers", ""))
        result["pullback_tiers"] = _parse_tiers(result.get("pullback_tiers", ""))

        return {"ok": True, "fund": result, "historyId": history_id}

    except HTTPException:
        raise
    except Exception as e:
        logger.error("执行操作失败: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"操作执行失败: {str(e)}")
    finally:
        conn.close()


@router.post("/undo/{history_id}")
async def undo_action(history_id: str, user_id: str = Depends(_uid)):
    """撤回指定操作记录，恢复基金到操作前状态"""
    conn = get_db()
    try:
        row = conn.execute(
            "SELECT * FROM history WHERE id = ? AND user_id = ?", (history_id, user_id)
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="操作记录不存在")
        row = dict(row)

        snapshot = row.get("snapshot_before")
        if not snapshot:
            raise HTTPException(status_code=400, detail="该操作记录没有撤回快照（可能为旧数据）")

        import json
        try:
            before = json.loads(snapshot)
        except json.JSONDecodeError:
            raise HTTPException(status_code=500, detail="撤回快照数据损坏")

        fund_name = row["fund_name"]
        fund = conn.execute(
            "SELECT * FROM funds WHERE name = ? AND user_id = ?", (fund_name, user_id)
        ).fetchone()
        if not fund:
            raise HTTPException(status_code=404, detail="对应基金不存在，可能已被删除")

        fund = dict(fund)
        conn.execute(
            """UPDATE funds SET total_buy_amount=?, total_sell_amount=?,
               current_market_value=?, current_return_rate=? WHERE name=? AND user_id=?""",
            (
                before["total_buy_amount"],
                before["total_sell_amount"],
                before["current_market_value"],
                before["current_return_rate"],
                fund_name,
                user_id,
            ),
        )
        # 删除该条历史记录
        conn.execute(
            "DELETE FROM history WHERE id = ? AND user_id = ?", (history_id, user_id)
        )
        conn.commit()

        updated = conn.execute(
            "SELECT * FROM funds WHERE name = ? AND user_id = ?", (fund_name, user_id)
        ).fetchone()
        result = dict(updated)
        result["add_tiers"] = _parse_tiers(result.get("add_tiers", ""))
        result["pullback_tiers"] = _parse_tiers(result.get("pullback_tiers", ""))
        return {"ok": True, "fund": result}

    except HTTPException:
        raise
    except Exception as e:
        logger.error("撤回操作失败: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"撤回失败: {str(e)}")
    finally:
        conn.close()


# ==================== AI 智能推荐加仓档位 ====================

@router.post("/ai-recommend-tiers")
async def ai_recommend_tiers(req: "TierRecommendRequest"):
    """AI 根据基金的初始本金、投入上限、当前收益 + 宏观政策分析，生成合理的金字塔加仓档位"""
    import asyncio
    from app.config import settings
    if not settings.llm_configured:
        raise HTTPException(status_code=503, detail="服务端未配置 LLM API Key")

    from app.agent import recommend_add_tiers, analyze_fund_macro
    from app.fund_api import get_fund_realtime_context, format_realtime_context
    try:
        data = req.model_dump(by_alias=True)
        fund_name = data["fundName"]
        loop = asyncio.get_running_loop()

        # 抓取实时市场数据（净值趋势 + 大盘行情），注入宏观分析，弥补 LLM 知识截止日期
        rt_text, rt_date = "", ""
        fund_code = (data.get("fundCode") or "").strip()
        if fund_code:
            try:
                rt_ctx = await get_fund_realtime_context(fund_code)
                rt_text = format_realtime_context(rt_ctx)
                rt_date = rt_ctx.get("nav_date", "")
            except Exception as e:
                logger.warning("获取实时市场数据失败（降级为纯 LLM 分析）: %s", e)

        # 并发执行：宏观分析 + 档位推荐同时进行，总耗时 = max(宏观, 档位) 而非 sum(宏观 + 档位)
        macro_future = loop.run_in_executor(None, analyze_fund_macro, fund_name, rt_text)
        tier_future = loop.run_in_executor(
            None,
            recommend_add_tiers,
            data["fundName"],
            data["totalBuyAmount"],
            data["initialPrincipal"],
            data["maxInvestment"],
            data["currentReturnRate"],
            data["currentMarketValue"],
            data.get("holdDays", 0),
            None,  # 先不传宏观分析，档位推荐独立运行
        )

        # 等待两个任务完成（并行等待，总时间取最长的那个）
        macro, result = await asyncio.gather(macro_future, tier_future, return_exceptions=True)

        # 处理档位推荐异常
        if isinstance(result, Exception):
            if isinstance(result, RuntimeError):
                raise HTTPException(status_code=503, detail=str(result))
            raise HTTPException(status_code=500, detail=f"AI 档位推荐失败: {result}")

        # 处理宏观分析结果
        if isinstance(macro, Exception) or (isinstance(macro, dict) and macro.get("error")):
            error_msg = str(macro) if isinstance(macro, Exception) else macro.get("message", "未知错误")
            logger.warning("宏观分析失败（并发模式）：%s", error_msg)
            result["macroAnalysis"] = {"error": True, "message": error_msg} if isinstance(macro, dict) and macro.get("error") else {"error": True, "message": error_msg, "sector": "未知", "policyScore": 50, "keyPolicies": [], "trend": "", "aggressiveness": 0, "analysis": "宏观分析超时或失败"}
        else:
            logger.info("宏观分析完成: %s -> 行业=%s 政策评分=%d", fund_name, macro.get("sector"), macro.get("policyScore"))
            result["macroAnalysis"] = {
                "sector": macro.get("sector", ""),
                "policyScore": macro.get("policyScore", 50),
                "keyPolicies": macro.get("keyPolicies", []),
                "trend": macro.get("trend", ""),
                "aggressiveness": macro.get("aggressiveness", 0),
                "analysis": macro.get("analysis", ""),
                "dataDate": rt_date if rt_text else "",
            }

        return result
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))


def _run_llm_stream_filter(llm_generator, content_queue, error_holder, full_text_list):
    """后台线程：消费 LLM 流，将分析文本放入队列，同时累积 JSON 文本。

    分离策略：
    1. 优先用分隔符 "::JSON::"（Prompt 已要求 LLM 在 JSON 前输出）
    2. 若 LLM 未输出分隔符，则兜底用 brace 计数从累积文本中提取 JSON
    """
    delimiter = "::JSON::"
    delim_len = len(delimiter)
    buffer = ""
    in_json = False

    def _fallback_brace_extract(text: str):
        """没有分隔符时，从 text 里用 brace 计数抠出 JSON 并放入 full_text_list"""
        depth = 0
        in_string = False
        escaped = False
        start = -1
        for i, ch in enumerate(text):
            if start == -1:
                if ch == '{':
                    start = i
                    depth = 1
                continue
            if escaped:
                escaped = False
                continue
            if ch == "\\":
                escaped = True
                continue
            if ch == '"':
                in_string = not in_string
                continue
            if in_string:
                continue
            if ch == '{':
                depth += 1
            elif ch == '}':
                depth -= 1
                if depth == 0:
                    full_text_list.append(text[start:i + 1])
                    return True
        return False

    try:
        for chunk in llm_generator:
            if chunk == '__REASONING__':
                if buffer:
                    content_queue.put(buffer)
                    buffer = ""
                content_queue.put('__REASONING__')
                continue

            if in_json:
                # 分隔符已出现，之后全部视为 JSON
                full_text_list.append(chunk)
                continue

            buffer += chunk
            idx = buffer.find(delimiter)
            if idx != -1:
                # 找到分隔符
                if idx > 0:
                    content_queue.put(buffer[:idx])
                full_text_list.append(buffer[idx + delim_len:])
                buffer = ""
                in_json = True
            else:
                # 还没找到分隔符，把不可能包含部分分隔符的前段安全地 flush 出去
                # 保留 delim_len - 1 个字符以处理跨 chunk 的分隔符
                if len(buffer) > delim_len - 1:
                    safe_flush = len(buffer) - delim_len + 1
                    content_queue.put(buffer[:safe_flush])
                    buffer = buffer[safe_flush:]
    except Exception as e:
        logger.error("LLM 流式过滤线程异常: %s", e)
        error_holder.append(e)
    finally:
        # 流结束仍未切到 JSON：buffer 里要么是纯文本（没有 JSON），要么混着 JSON
        if buffer:
            if not in_json:
                # 尝试兜底提取 JSON；剩下的作为 content
                if not _fallback_brace_extract(buffer):
                    content_queue.put(buffer)
            else:
                full_text_list.append(buffer)
        content_queue.put(None)  # 结束标志


def _default_tier_strategy(initial_principal: float, total_buy_amount: float,
                           max_investment: float, current_return_rate: float) -> dict:
    """当 AI 返回无法解析时，生成一组合理的默认档位。"""
    remaining = max(0.0, (max_investment or 0) - (total_buy_amount or 0))
    if initial_principal <= 0:
        initial_principal = remaining or 10000

    coverage = remaining / initial_principal if initial_principal > 0 else 0

    # 根据预算覆盖率和盈亏状态确定总比例
    if current_return_rate > 0:
        base_total = 0.30
        strategy_type = "pullback"
    elif current_return_rate > -10:
        base_total = 0.40
        strategy_type = "downside"
    elif current_return_rate > -25:
        base_total = 0.55
        strategy_type = "downside"
    else:
        base_total = 0.70
        strategy_type = "downside"

    # 预算越充裕越激进
    if coverage >= 10:
        base_total = min(3.0, base_total * 3)
    elif coverage >= 5:
        base_total = min(2.0, base_total * 2)
    elif coverage >= 2:
        base_total = min(1.0, base_total * 1.3)
    elif coverage >= 1:
        pass
    elif coverage >= 0.5:
        base_total *= 0.7
    else:
        base_total *= 0.4

    # 生成 4 档金字塔比例
    total_ratio = base_total * 100  # 转成百分比
    ratios = [
        round(total_ratio * 0.15, 1),
        round(total_ratio * 0.25, 1),
        round(total_ratio * 0.30, 1),
        round(total_ratio * 0.30, 1),
    ]

    # 档位 line
    if strategy_type == "pullback":
        lines = [-2, -5, -9, -14]
    else:
        lines = [-8, -14, -21, -30]

    tiers = [{"line": lines[i], "ratio": ratios[i]} for i in range(4)]

    return {
        "strategyType": strategy_type,
        "tiers": tiers,
        "pullbackTiers": [],
        "stopProfitLine": 20,
        "stopLossLine": -30,
        "stopProfitRatio": 20,
        "stopLossRatio": 60,
        "strategyStyle": "预算平衡型" if coverage >= 1 else "保守防御型",
        "explanation": "AI 输出解析异常，已根据您的预算和当前收益率生成默认金字塔加仓方案。",
    }


@router.post("/ai-recommend-tiers/stream")
async def ai_recommend_tiers_stream(req: "TierRecommendRequest"):
    """AI 智能推荐加仓档位（流式 SSE）

    两阶段串行输出：
    【阶段1】宏观政策分析（流式打字机）
    【阶段2】加仓策略 + 档位比例（流式打字机，含 JSON 解析→自动填充表单）

    协议事件：
    - { connected: true }             – 连接确认
    - { status: "macro_analyzing" }   – 开始宏观分析
    - { macroContent: "..." }         – 宏观分析文本（打字机逐字）
    - { status: "generating_strategy" } – 开始策略生成
    - { content: "..." }              – 策略分析文本（打字机逐字）
    - { reasoning: true }             – AI 思考阶段
    - { phase: "macro"|"tier" }       – 标记当前阶段
    - { done: true, result: {...}}    – 完成 + 解析结果
    """
    from app.config import settings
    if not settings.llm_configured:
        raise HTTPException(status_code=503, detail="服务端未配置 LLM API Key")

    from app.agent import recommend_add_tiers_stream, analyze_fund_macro_stream, _safe_parse_json, _brute_parse_json
    from app.fund_api import get_fund_realtime_context, format_realtime_context
    import threading
    from queue import Queue as TQueue

    data = req.model_dump(by_alias=True)
    fund_name = data["fundName"]

    async def event_stream():
        loop = asyncio.get_running_loop()

        logger.info("[SSE AiRecommend] 发送 connected 事件")
        yield f"data: {json.dumps({'connected': True}, ensure_ascii=False)}\n\n"

        # 抓取实时市场数据（净值趋势 + 大盘行情），注入宏观分析，弥补 LLM 知识截止日期
        rt_text, rt_date = "", ""
        fund_code = (data.get("fundCode") or "").strip()
        if fund_code:
            try:
                rt_ctx = await get_fund_realtime_context(fund_code)
                rt_text = format_realtime_context(rt_ctx)
                rt_date = rt_ctx.get("nav_date", "")
                if rt_text:
                    logger.info("[SSE AiRecommend] 实时市场数据已获取（净值截至 %s），注入宏观分析", rt_date)
            except Exception as e:
                logger.warning("[SSE AiRecommend] 获取实时市场数据失败（降级为纯 LLM 分析）: %s", e)

        # ========== 阶段 1：宏观政策分析（流式） ==========
        logger.info("[SSE AiRecommend] 阶段1: 开始宏观分析")
        yield f"data: {json.dumps({'status': 'macro_analyzing'}, ensure_ascii=False)}\n\n"

        macro_content_queue = TQueue()
        macro_full_text = []
        macro_error = []

        macro_thread = threading.Thread(
            target=_run_llm_stream_filter,
            args=(analyze_fund_macro_stream(fund_name, rt_text), macro_content_queue,
                  macro_error, macro_full_text),
            daemon=True,
        )
        macro_thread.start()

        # 流式输出宏观分析文本
        while True:
            chunk = await loop.run_in_executor(None, macro_content_queue.get)
            if chunk is None:
                break
            if chunk == '__REASONING__':
                yield f"data: {json.dumps({'reasoning': True, 'phase': 'macro'}, ensure_ascii=False)}\n\n"
            elif chunk.strip():
                yield f"data: {json.dumps({'macroContent': chunk, 'phase': 'macro'}, ensure_ascii=False)}\n\n"

        macro_thread.join(timeout=5)

        if macro_error:
            logger.warning("[SSE AiRecommend] 宏观分析流失败: %s", macro_error[0])

        # 解析宏观分析 JSON
        macro_result = None
        try:
            full_text = "".join(macro_full_text)
            if full_text.strip():
                parsed = _safe_parse_json(full_text)
                macro_result = {
                    "sector": parsed.get("sector", "未知"),
                    "policyScore": parsed.get("policyScore", 50),
                    "keyPolicies": parsed.get("keyPolicies", []),
                    "trend": parsed.get("trend", ""),
                    "aggressiveness": parsed.get("aggressiveness", 0),
                    "analysis": parsed.get("analysis", ""),
                    "dataDate": rt_date if rt_text else "",
                }
                logger.info("[SSE AiRecommend] 宏观分析 JSON 解析成功: sector=%s, score=%s",
                            macro_result["sector"], macro_result["policyScore"])
        except Exception as e:
            logger.warning("[SSE AiRecommend] 宏观分析 JSON 解析失败: %s", e)

        if macro_result is None:
            macro_result = {"error": True, "message": macro_error[0] if macro_error else "宏观分析未返回有效数据"}

        # ========== 阶段 2：加仓策略 + 档位推荐（流式） ==========
        logger.info("[SSE AiRecommend] 阶段2: 开始策略生成")
        yield f"data: {json.dumps({'status': 'generating_strategy'}, ensure_ascii=False)}\n\n"

        tier_content_queue = TQueue()
        tier_full_text = []
        tier_error = []

        tier_thread = threading.Thread(
            target=_run_llm_stream_filter,
            args=(
                recommend_add_tiers_stream(
                    fund_name=data["fundName"],
                    total_buy_amount=data["totalBuyAmount"],
                    initial_principal=data["initialPrincipal"],
                    max_investment=data["maxInvestment"],
                    current_return_rate=data["currentReturnRate"],
                    current_market_value=data["currentMarketValue"],
                    hold_days=data.get("holdDays", 0),
                    macro_analysis=macro_result if not macro_result.get("error") else None,
                ),
                tier_content_queue,
                tier_error,
                tier_full_text,
            ),
            daemon=True,
        )
        tier_thread.start()

        # 流式输出策略分析文本
        while True:
            chunk = await loop.run_in_executor(None, tier_content_queue.get)
            if chunk is None:
                break
            if chunk == '__REASONING__':
                yield f"data: {json.dumps({'reasoning': True, 'phase': 'tier'}, ensure_ascii=False)}\n\n"
            elif chunk.strip():
                yield f"data: {json.dumps({'content': chunk, 'phase': 'tier'}, ensure_ascii=False)}\n\n"

        tier_thread.join(timeout=5)

        if tier_error:
            logger.error("[SSE AiRecommend] 档位推荐失败: %s", tier_error[0])
            yield f"data: {json.dumps({'error': str(tier_error[0])}, ensure_ascii=False)}\n\n"
            return

        # 解析档位推荐 JSON
        full_text = "".join(tier_full_text)
        logger.info("[SSE AiRecommend] 流式完成，完整文本长度 %d 字符", len(full_text))
        tier_result = None
        try:
            if full_text.strip():
                tier_result = _safe_parse_json(full_text)
        except Exception as e:
            logger.warning("安全解析 JSON 失败: %s", e)

        if not tier_result or not tier_result.get("tiers"):
            logger.warning("安全解析未提取到 tiers，尝试暴力兜底")
            try:
                tier_result = _brute_parse_json(full_text)
            except Exception as e:
                logger.warning("暴力解析 JSON 也失败: %s", e)

        if not tier_result or not tier_result.get("tiers"):
            logger.error("AI 档位 JSON 无法解析，使用默认档位兜底。原始文本(前200字符): %s", full_text[:200])
            tier_result = _default_tier_strategy(
                initial_principal=data["initialPrincipal"],
                total_buy_amount=data["totalBuyAmount"],
                max_investment=data["maxInvestment"],
                current_return_rate=data["currentReturnRate"],
            )
            # 给前端一个温和提示，不再阻断流程
            yield f"data: {json.dumps({'warning': 'AI 推荐数据格式异常，已使用默认档位方案，请检查并手动调整。'}, ensure_ascii=False)}\n\n"

        # 组装最终结果
        result_data = {
            "strategyType": tier_result.get("strategyType", "downside"),
            "tiers": tier_result.get("tiers", []),
            "pullbackTiers": tier_result.get("pullbackTiers", []),
            "stopProfitLine": tier_result.get("stopProfitLine", 0),
            "stopLossLine": tier_result.get("stopLossLine", 0),
            "stopProfitRatio": tier_result.get("stopProfitRatio", 0),
            "stopLossRatio": tier_result.get("stopLossRatio", 0),
            "strategyStyle": tier_result.get("strategyStyle", ""),
            "explanation": tier_result.get("explanation", ""),
        }

        # 附加宏观分析结构化数据
        if macro_result and not macro_result.get("error"):
            result_data["macroAnalysis"] = macro_result
        else:
            result_data["macroAnalysis"] = {
                "error": True,
                "message": macro_result.get("message", "未知错误") if macro_result else "宏观分析未执行",
            }

        logger.info("[SSE AiRecommend] 两阶段流程完成，发送 done + result")
        yield f"data: {json.dumps({'done': True, 'result': result_data}, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no", "Connection": "keep-alive"},
    )


@router.post("/overall-analysis", response_model=OverallAnalysisResponse)
async def overall_analysis(req: "OverallAnalysisRequest"):
    """AI 对全部基金持仓进行整体分析并给出操作建议"""
    import asyncio
    from app.config import settings
    if not settings.llm_configured:
        raise HTTPException(status_code=503, detail="服务端未配置 LLM API Key")

    from app.agent import analyze_overall_portfolio
    try:
        loop = asyncio.get_running_loop()
        analysis = await loop.run_in_executor(
            None, analyze_overall_portfolio, req.portfolio_text
        )
        return OverallAnalysisResponse(analysis=analysis)
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))


@router.post("/overall-analysis/stream")
async def overall_analysis_stream(req: "OverallAnalysisRequest"):
    """AI 对全部基金持仓进行整体分析（流式 SSE）"""
    from app.config import settings
    if not settings.llm_configured:
        raise HTTPException(status_code=503, detail="服务端未配置 LLM API Key")

    from app.agent import analyze_overall_portfolio_stream
    import threading
    from queue import Queue as TQueue

    async def event_stream():
        chunk_queue = TQueue()
        error_holder = []
        first_chunk_flag = [True]

        def _run():
            logger.info("[SSE] 后台线程启动，开始调用 LLM...")
            try:
                for chunk in analyze_overall_portfolio_stream(req.portfolio_text):
                    if first_chunk_flag[0]:
                        logger.info("[SSE] 收到首个 LLM 内容块 (长度=%d)", len(chunk))
                        first_chunk_flag[0] = False
                    chunk_queue.put(chunk)
            except Exception as e:
                logger.error("[SSE] LLM 调用异常: %s", e)
                error_holder.append(e)
            finally:
                logger.info("[SSE] 后台线程结束")
                chunk_queue.put(None)

        thread = threading.Thread(target=_run, daemon=True)
        thread.start()

        logger.info("[SSE] 发送 connected 事件")
        yield f"data: {json.dumps({'connected': True}, ensure_ascii=False)}\n\n"

        loop = asyncio.get_running_loop()
        while True:
            chunk = await loop.run_in_executor(None, chunk_queue.get)
            if chunk is None:
                break
            if chunk == '__REASONING__':
                # 推理阶段开始，通知前端显示"思考中"
                yield f"data: {json.dumps({'reasoning': True}, ensure_ascii=False)}\n\n"
            else:
                yield f"data: {json.dumps({'content': chunk}, ensure_ascii=False)}\n\n"

        thread.join(timeout=5)

        if error_holder:
            logger.error("[SSE] 流式整体分析失败: %s", error_holder[0])
            yield f"data: {json.dumps({'error': str(error_holder[0])}, ensure_ascii=False)}\n\n"
            return

        logger.info("[SSE] 流式分析正常结束，发送 done")
        yield f"data: {json.dumps({'content': '', 'done': True}, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )
