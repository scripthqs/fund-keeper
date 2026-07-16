"""中国节假日 / 交易日判断路由"""

from datetime import date, datetime, time, timedelta

from fastapi import APIRouter

try:
    from chinese_calendar import is_workday, is_holiday, get_holiday_detail
    HAS_CHINESE_CALENDAR = True
except ImportError:
    HAS_CHINESE_CALENDAR = False

router = APIRouter(prefix="/api/calendar", tags=["calendar"])


@router.get("/trading-status")
async def trading_status():
    """
    返回今日交易状态：
      - trading: 是否可交易（非周末、非法定节假日）
      - holiday: 是否是法定节假日
      - holiday_name: 节假日名称（如 "春节"）
      - next_trading_day: 下一个交易日（YYYY-MM-DD）
      - cutoff_remaining: 距15:00还剩多少秒（仅 trading=true 时有意义）
    """
    today = date.today()
    now = datetime.now()
    day_of_week = today.weekday()  # 0=Mon, 6=Sun

    if HAS_CHINESE_CALENDAR:
        # 使用 chinese-calendar 精确判断（含调休）
        try:
            trading = is_workday(today)
            holiday_flag = is_holiday(today)
            _, holiday_name = get_holiday_detail(today) if holiday_flag else (False, "")
        except Exception:
            trading = day_of_week < 5
            holiday_flag = False
            holiday_name = ""
    else:
        # 降级：仅判断周末
        trading = day_of_week < 5
        holiday_flag = False
        holiday_name = ""

    # 计算距 15:00 的剩余秒数
    cutoff = datetime.combine(today, time(15, 0))
    cutoff_remaining = max(0, int((cutoff - now).total_seconds())) if trading else 0

    # 计算下一个交易日
    next_day = today + timedelta(days=1)
    for _ in range(30):
        if HAS_CHINESE_CALENDAR:
            try:
                if is_workday(next_day):
                    break
            except Exception:
                if next_day.weekday() < 5:
                    break
        else:
            if next_day.weekday() < 5:
                break
        next_day += timedelta(days=1)

    return {
        "today": today.isoformat(),
        "trading": trading,
        "holiday": holiday_flag,
        "holiday_name": holiday_name or "",
        "cutoff_remaining": cutoff_remaining,
        "next_trading_day": next_day.isoformat(),
        "has_library": HAS_CHINESE_CALENDAR,
    }
