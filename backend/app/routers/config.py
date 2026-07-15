"""投资配置路由"""

import json

from fastapi import APIRouter

from app.database import get_db, DEFAULT_CONFIG
from app.models import ConfigUpdate

router = APIRouter(prefix="/api/config", tags=["投资配置"])


@router.get("")
async def get_config():
    """获取投资配置"""
    conn = get_db()
    row = conn.execute(
        "SELECT data FROM config WHERE id = 'default'"
    ).fetchone()
    conn.close()

    if row:
        config = json.loads(row["data"])
    else:
        config = DEFAULT_CONFIG.copy()

    return config


@router.put("")
async def update_config(config: ConfigUpdate):
    """更新投资配置"""
    data = config.model_dump(by_alias=True, exclude_none=True)

    # 合并到现有配置（保留 peakReturnRate 等字段）
    conn = get_db()
    row = conn.execute(
        "SELECT data FROM config WHERE id = 'default'"
    ).fetchone()

    if row:
        existing = json.loads(row["data"])
    else:
        existing = DEFAULT_CONFIG.copy()

    existing.update(data)
    conn.execute(
        "UPDATE config SET data = ? WHERE id = 'default'",
        (json.dumps(existing, ensure_ascii=False),),
    )
    conn.commit()
    conn.close()

    return existing


@router.put("/peak-return")
async def update_peak_return(fund_id: str, peak_rate: float):
    """更新某基金的最高收益率快照（用于移动止盈）"""
    conn = get_db()
    row = conn.execute(
        "SELECT data FROM config WHERE id = 'default'"
    ).fetchone()

    if row:
        config = json.loads(row["data"])
    else:
        config = DEFAULT_CONFIG.copy()

    if "peakReturnRate" not in config:
        config["peakReturnRate"] = {}
    config["peakReturnRate"][fund_id] = peak_rate

    conn.execute(
        "UPDATE config SET data = ? WHERE id = 'default'",
        (json.dumps(config, ensure_ascii=False),),
    )
    conn.commit()
    conn.close()

    return config["peakReturnRate"]
