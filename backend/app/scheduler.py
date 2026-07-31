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

# 北京时间 = UTC+8，每天晚上 22:00 执行（此时绝大多数基金已公布结算净值）
SCHEDULE_HOUR = 22
SCHEDULE_MINUTE = 0

# 后台任务引用，用于优雅关闭
_background_task: Optional[asyncio.Task] = None


async def _update_single_fund(fund: dict, user_id: str, beijing_today: str) -> dict | None:
    """更新单只基金的当日收益（基于份额 × 已结算净值精确计算），返回快照数据或 None"""
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
    total_shares = fund.get("total_shares", 0) or 0
    yesterday_nav = fund.get("yesterday_nav", 0) or 0

    try:
        info = await query_fund_by_code(code)
    except FundQueryError as e:
        logger.warning("定时更新 - 基金 %s (%s) 查询失败: %s", fund_id, fund_name, e)
        return None
    except Exception as e:
        logger.error("定时更新 - 基金 %s (%s) 查询异常: %s", fund_id, fund_name, e)
        return None

    # 只使用已结算净值（东方财富），不使用实时估值
    settled_nav = info.get("nav", 0)
    settled_nav_date = info.get("date", "")

    # 当日结算净值未公布时跳过
    if settled_nav_date < beijing_today or settled_nav <= 0:
        logger.info(
            "定时更新 - 基金 %s (%s) 最新净值日期=%s < 今天=%s，跳过（净值尚未公布）",
            fund_id, fund_name, settled_nav_date, beijing_today,
        )
        return None

    # 旧数据初始化：份额为0时用当前市值反推（一次性）
    if total_shares <= 0 and old_market_value > 0:
        total_shares = round(old_market_value / settled_nav, 4)
        logger.info(
            "定时更新 - 旧数据初始化: 基金 %s (%s) 份额=%.4f（市值%.2f / NAV %.4f）",
            fund_id, fund_name, total_shares, old_market_value, settled_nav,
        )

    if total_shares <= 0:
        logger.warning("定时更新 - 基金 %s (%s) 份额为0，无法计算市值，跳过", fund_id, fund_name)
        return None

    # 检查今日是否有买入记录，若买入时用的是估算净值（nav_at_action ≠ 今日结算净值），
    # 则用今日结算净值纠正份额，确保每笔买入的份额精确
    conn_check = get_db()
    try:
        today_buys = conn_check.execute(
            "SELECT amount, nav_at_action FROM history WHERE fund_name=? AND date=? AND type='买入' AND user_id=?",
            (fund_name, beijing_today, user_id),
        ).fetchall()
        for buy in today_buys:
            buy_amount = buy["amount"] or 0
            estimated_nav = buy["nav_at_action"] or 0
            if estimated_nav > 0 and buy_amount > 0 and abs(estimated_nav - settled_nav) > 0.0001:
                estimated_shares = round(buy_amount / estimated_nav, 4)
                correct_shares = round(buy_amount / settled_nav, 4)
                correction = round(correct_shares - estimated_shares, 4)
                if abs(correction) > 0:
                    total_shares = round(total_shares + correction, 4)
                    logger.info(
                        "定时更新 - 纠正 %s 今日买入份额: 估算NAV %.4f→实际NAV %.4f, "
                        "份额 %.4f→%.4f (调整%+.4f)",
                        fund_name, estimated_nav, settled_nav,
                        estimated_shares, correct_shares, correction,
                    )
    except Exception as e:
        logger.warning("定时更新 - 查询今日买入记录失败 %s: %s", fund_id, e)
    finally:
        conn_check.close()

    # 核心公式：市值 = 份额 × 净值，收益 = 份额 × (今日净值 - 昨日净值)
    new_market_value = round(total_shares * settled_nav, 2)

    if yesterday_nav > 0:
        today_profit = round(total_shares * (settled_nav - yesterday_nav), 2)
        today_change = round((settled_nav - yesterday_nav) / yesterday_nav * 100, 4)
    else:
        # 第一天运行：建立基线，不计算收益
        today_profit = 0.0
        today_change = None
        logger.info("定时更新 - 基金 %s (%s) 首次更新（昨日净值=0），建立基线", fund_id, fund_name)

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
        "定时更新 - %s (%s): 份额=%.4f 今日NAV=%s 昨日NAV=%s 涨跌=%s%% 市值 %s→%s 收益=%s 收益率 %s→%s%%",
        fund_id, fund_name, total_shares,
        settled_nav, yesterday_nav,
        f"{today_change:+.2f}" if today_change is not None else "N/A",
        old_market_value, new_market_value,
        f"{today_profit:+.2f}",
        old_return_rate, new_return_rate,
    )

    # 写入数据库（包含份额和昨日净值以便下次计算）
    conn = get_db()
    try:
        conn.execute(
            """UPDATE funds SET
               current_market_value=?, current_return_rate=?, last_nav_update=?,
               total_shares=?, yesterday_nav=?
               WHERE id=? AND user_id=?""",
            (new_market_value, new_return_rate, now_str(),
             total_shares, settled_nav, fund_id, user_id),
        )

        # 保存每日快照（同一天覆盖更新）
        today = beijing_today
        existing = conn.execute(
            "SELECT id FROM snapshots WHERE fund_id=? AND date=? AND user_id=?",
            (fund_id, today, user_id),
        ).fetchone()

        snap_change = today_change if today_change is not None else 0
        if existing:
            conn.execute(
                """UPDATE snapshots SET
                   safety_cushion=?, recovery_needed=?, today_change=?, total_return=?,
                   daily_profit=?, nav=?
                   WHERE fund_id=? AND date=? AND user_id=?""",
                (0, 0, snap_change, new_return_rate,
                 today_profit, settled_nav,
                 fund_id, today, user_id),
            )
        else:
            conn.execute(
                """INSERT INTO snapshots
                   (id, fund_id, user_id, date, safety_cushion, recovery_needed,
                    today_change, total_return, daily_profit, nav)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (gen_id(), fund_id, user_id, today, 0, 0,
                 snap_change, new_return_rate, today_profit, settled_nav),
            )

        # 写入操作历史（自动更新记录）
        if today_change is not None:
            profit_note = (
                f"今日收益 {today_profit:+.2f} 元（NAV {yesterday_nav}→{settled_nav}，"
                f"涨跌 {today_change:+.2f}%，份额 {total_shares:.2f}）"
            )
        else:
            profit_note = f"基线建立：NAV={settled_nav}，份额={total_shares:.2f}"
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
        "total_shares": total_shares,
        "settled_nav": settled_nav,
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
