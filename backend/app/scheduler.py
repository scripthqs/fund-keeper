"""
定时任务调度模块（纯 asyncio 实现，无需第三方依赖）
每天晚间自动更新所有用户的基金当日收益、净值、快照
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Optional

from app.database import get_db, gen_id, now_str
from app.fund_api import query_fund_by_code, FundQueryError

logger = logging.getLogger(__name__)

# 北京时间 = UTC+8，每天晚上 20:00 执行（收盘后净值基本已更新）
SCHEDULE_HOUR = 20
SCHEDULE_MINUTE = 0

# 后台任务引用，用于优雅关闭
_background_task: Optional[asyncio.Task] = None


async def _update_single_fund(fund: dict, user_id: str, beijing_today: str) -> dict | None:
    """更新单只基金的当日收益，返回快照数据或 None"""
    code = (fund.get("fund_code") or "").strip()
    if not code:
        logger.info("基金 %s (%s) 无基金代码，跳过定时更新", fund["id"], fund.get("name", ""))
        return None

    fund_id = fund["id"]
    fund_name = fund.get("name", "")
    old_market_value = fund.get("current_market_value", 0)
    old_return_rate = fund.get("current_return_rate", 0)
    total_buy = fund.get("total_buy_amount", 0)
    total_sell = fund.get("total_sell_amount", 0)

    try:
        info = await query_fund_by_code(code)
    except FundQueryError as e:
        logger.warning("定时更新 - 基金 %s (%s) 查询失败: %s", fund_id, fund_name, e)
        return None
    except Exception as e:
        logger.error("定时更新 - 基金 %s (%s) 查询异常: %s", fund_id, fund_name, e)
        return None

    # 确定用于计算市值的净值：
    # 盘中（已结算净值日期 < 北京今天）且新浪实时估值可用 → 用估值净值
    # 当晚净值已结算（date == 今天）→ 用已结算净值
    settled_nav_date = info.get("date", "")
    estimated_nav = info.get("estimated_nav") or 0
    use_estimate = estimated_nav > 0 and settled_nav_date < beijing_today
    nav_for_calc = estimated_nav if use_estimate else info.get("nav", 0)
    nav_label = "实时估值" if use_estimate else "已结算净值"

    # 今日涨跌幅（%）
    today_change = info.get("estimated_change")

    # 计算今日收益金额
    if today_change is not None and old_market_value > 0:
        today_profit = round(old_market_value * today_change / 100, 2)
        new_market_value = round(old_market_value + today_profit, 2)
    else:
        # 无涨跌幅数据：尝试用净值反推
        today_profit = 0.0
        new_market_value = old_market_value
        # 如果 old_market_value 为 0 但有份额，尝试用净值估算市值
        if old_market_value == 0 and nav_for_calc > 0 and total_buy > 0:
            # 用总买入金额推算份额，再算市值（粗略估算）
            if total_buy > 0:
                # 无法准确推算份额，保持原值
                pass

    # 确保市值不为负
    new_market_value = max(0, new_market_value)

    # 计算新的收益率
    if total_buy > 0:
        new_return_rate = round(
            (new_market_value - total_buy + total_sell) / total_buy * 100, 2
        )
    else:
        new_return_rate = old_return_rate

    logger.info(
        "定时更新 - %s (%s): %s=%s 涨跌=%s%% 市值 %s→%s 收益=%s 收益率 %s→%s%%",
        fund_id, fund_name,
        nav_label, nav_for_calc,
        today_change if today_change is not None else "N/A",
        old_market_value, new_market_value,
        today_profit,
        old_return_rate, new_return_rate,
    )

    # 写入数据库
    conn = get_db()
    try:
        conn.execute(
            """UPDATE funds SET
               current_market_value=?, current_return_rate=?, last_nav_update=?
               WHERE id=? AND user_id=?""",
            (new_market_value, new_return_rate, now_str(), fund_id, user_id),
        )

        # 保存每日快照（同一天覆盖更新），含收益金额和净值
        today = beijing_today
        existing = conn.execute(
            "SELECT id FROM snapshots WHERE fund_id=? AND date=? AND user_id=?",
            (fund_id, today, user_id),
        ).fetchone()

        if existing:
            conn.execute(
                """UPDATE snapshots SET
                   safety_cushion=?, recovery_needed=?, today_change=?, total_return=?,
                   daily_profit=?, nav=?
                   WHERE fund_id=? AND date=? AND user_id=?""",
                (0, 0, today_change or 0, new_return_rate,
                 today_profit, nav_for_calc,
                 fund_id, today, user_id),
            )
        else:
            conn.execute(
                """INSERT INTO snapshots
                   (id, fund_id, user_id, date, safety_cushion, recovery_needed,
                    today_change, total_return, daily_profit, nav)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (gen_id(), fund_id, user_id, today, 0, 0,
                 today_change or 0, new_return_rate, today_profit, nav_for_calc),
            )

        # 写入操作历史（自动更新记录）
        profit_note = f"今日收益 {today_profit:+.2f} 元（涨跌 {today_change:+.2f}%）" if today_change is not None else "自动更新净值"
        conn.execute(
            """INSERT INTO history
               (id, date, fund_name, type, amount, return_rate, note, created_at, user_id)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (gen_id(), today, fund_name, "自动更新", today_profit,
             new_return_rate, profit_note, now_str(), user_id),
        )

        conn.commit()
    except Exception as e:
        logger.error("定时更新 - 写入数据库失败 %s: %s", fund_id, e)
    finally:
        conn.close()

    return {
        "fund_id": fund_id,
        "fund_name": fund_name,
        "today_change": today_change,
        "today_profit": today_profit,
        "new_market_value": new_market_value,
        "new_return_rate": new_return_rate,
    }


async def daily_profit_update_job():
    """定时任务：每天晚上自动更新所有用户基金的当日收益"""
    beijing_now = datetime.utcnow() + timedelta(hours=8)
    beijing_today = beijing_now.strftime("%Y-%m-%d")
    logger.info("====== 开始执行每日收益自动更新 (%s 北京时间) ======", beijing_now.strftime("%H:%M"))

    conn = get_db()
    try:
        # 获取所有有基金代码的用户
        funds_rows = conn.execute(
            "SELECT * FROM funds WHERE fund_code != '' AND fund_code IS NOT NULL ORDER BY user_id"
        ).fetchall()
    finally:
        conn.close()

    if not funds_rows:
        logger.info("定时更新 - 没有需要更新的基金")
        return

    # 按用户分组
    user_funds: dict[str, list[dict]] = {}
    for row in funds_rows:
        uid = row["user_id"] or ""
        if uid not in user_funds:
            user_funds[uid] = []
        user_funds[uid].append(dict(row))

    total_updated = 0
    total_failed = 0

    for user_id, funds in user_funds.items():
        logger.info("定时更新 - 处理用户 %s，共 %d 只基金", user_id or "默认用户", len(funds))
        # 逐个更新（避免对东方财富 API 并发过高被封）
        for fund in funds:
            try:
                result = await _update_single_fund(fund, user_id, beijing_today)
                if result:
                    total_updated += 1
                else:
                    total_failed += 1
            except Exception as e:
                logger.error("定时更新 - 基金 %s 更新异常: %s", fund.get("id", "?"), e)
                total_failed += 1
            # 每只基金之间间隔 2 秒，避免请求过于密集
            await asyncio.sleep(2)

    logger.info(
        "====== 每日收益自动更新完成: 成功 %d, 失败 %d ======",
        total_updated, total_failed,
    )


def _seconds_until_next(hour: int, minute: int) -> float:
    """计算距离下一次执行时间（北京时间）的秒数"""
    now_utc = datetime.utcnow()
    now_beijing = now_utc + timedelta(hours=8)

    # 今天的目标时间
    target = now_beijing.replace(hour=hour, minute=minute, second=0, microsecond=0)

    # 如果今天的目标时间已经过了，则取明天
    if target <= now_beijing:
        target += timedelta(days=1)

    delta = target - now_beijing
    seconds = delta.total_seconds()
    # 至少等待 10 秒（防止极端情况）
    return max(10.0, seconds)


async def _scheduler_loop():
    """后台调度循环：计算等待时间，到点执行任务"""
    logger.info(
        "定时任务调度器已启动，每天 %02d:%02d (北京时间) 自动更新当日收益",
        SCHEDULE_HOUR, SCHEDULE_MINUTE,
    )

    while True:
        try:
            wait_seconds = _seconds_until_next(SCHEDULE_HOUR, SCHEDULE_MINUTE)
            wait_hours = wait_seconds / 3600
            logger.info("距离下次每日收益更新还有 %.1f 小时", wait_hours)

            await asyncio.sleep(wait_seconds)

            # 执行定时任务
            await daily_profit_update_job()

        except asyncio.CancelledError:
            logger.info("定时任务调度器被取消")
            break
        except Exception as e:
            logger.error("定时任务调度异常: %s", e, exc_info=True)
            # 出错后等待 5 分钟再重试
            await asyncio.sleep(300)


def start_scheduler():
    """启动定时任务调度器（在 FastAPI startup 事件中调用）"""
    global _background_task

    if _background_task is not None and not _background_task.done():
        logger.warning("定时任务调度器已在运行中")
        return

    loop = asyncio.get_event_loop()
    _background_task = loop.create_task(_scheduler_loop())
    logger.info("定时任务后台协程已创建")


async def stop_scheduler():
    """停止定时任务调度器（在 FastAPI shutdown 事件中调用）"""
    global _background_task
    if _background_task is not None:
        _background_task.cancel()
        try:
            await _background_task
        except asyncio.CancelledError:
            pass
        _background_task = None
        logger.info("定时任务调度器已停止")
