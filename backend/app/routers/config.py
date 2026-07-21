"""投资配置路由"""

import json

from fastapi import APIRouter, Depends, Header

from app.database import get_db, DEFAULT_CONFIG, gen_id, get_current_user_id
from app.models import ConfigUpdate

router = APIRouter(prefix="/api/config", tags=["投资配置"])


async def _uid(x_username: str = Header(None, alias="X-Username")):
    return get_current_user_id(x_username)


def _ensure_config(conn, user_id: str) -> dict:
    """确保用户配置存在，不存在则创建默认配置"""
    row = conn.execute(
        "SELECT id, data FROM config WHERE user_id = ?", (user_id,)
    ).fetchone()
    if row:
        return json.loads(row["data"])
    # 创建默认配置
    cid = gen_id()
    data = json.dumps(DEFAULT_CONFIG, ensure_ascii=False)
    conn.execute(
        "INSERT INTO config (id, user_id, data) VALUES (?, ?, ?)", (cid, user_id, data)
    )
    conn.commit()
    return DEFAULT_CONFIG.copy()


@router.get("")
async def get_config(user_id: str = Depends(_uid)):
    """获取当前用户的投资配置"""
    conn = get_db()
    config = _ensure_config(conn, user_id)
    conn.close()
    return config


@router.put("")
async def update_config(config: ConfigUpdate, user_id: str = Depends(_uid)):
    """更新当前用户的投资配置"""
    data = config.model_dump(by_alias=True, exclude_none=True)

    conn = get_db()
    existing = _ensure_config(conn, user_id)
    existing.update(data)

    conn.execute(
        "UPDATE config SET data = ? WHERE user_id = ?",
        (json.dumps(existing, ensure_ascii=False), user_id),
    )
    conn.commit()
    conn.close()

    return existing


@router.put("/peak-return")
async def update_peak_return(fund_id: str, peak_rate: float, user_id: str = Depends(_uid)):
    """更新某基金的最高收益率快照（用于移动止盈）"""
    conn = get_db()
    config = _ensure_config(conn, user_id)

    if "peakReturnRate" not in config:
        config["peakReturnRate"] = {}
    config["peakReturnRate"][fund_id] = peak_rate

    conn.execute(
        "UPDATE config SET data = ? WHERE user_id = ?",
        (json.dumps(config, ensure_ascii=False), user_id),
    )
    conn.commit()
    conn.close()

    return config["peakReturnRate"]
