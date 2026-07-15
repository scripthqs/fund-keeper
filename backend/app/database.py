"""SQLite 数据库初始化与连接管理"""

import json
import sqlite3
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

from app.config import DB_PATH


def get_db() -> sqlite3.Connection:
    """获取数据库连接（每次请求创建新连接）"""
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db():
    """初始化数据库表结构"""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = get_db()
    cursor = conn.cursor()

    # 基金表
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS funds (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            initial_principal REAL DEFAULT 0,
            buy_date TEXT DEFAULT '',
            total_buy_amount REAL DEFAULT 0,
            total_sell_amount REAL DEFAULT 0,
            current_market_value REAL DEFAULT 0,
            current_return_rate REAL DEFAULT 0,
            created_at TEXT DEFAULT ''
        )
    """)

    # 配置表（单行，id 固定为 'default'）
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS config (
            id TEXT PRIMARY KEY DEFAULT 'default',
            data TEXT NOT NULL DEFAULT '{}'
        )
    """)

    # 操作历史表
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS history (
            id TEXT PRIMARY KEY,
            date TEXT NOT NULL,
            fund_name TEXT DEFAULT '',
            type TEXT DEFAULT '',
            amount REAL DEFAULT 0,
            return_rate REAL DEFAULT 0,
            note TEXT DEFAULT '',
            created_at TEXT DEFAULT ''
        )
    """)

    # 聊天消息表
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS chat_messages (
            id TEXT PRIMARY KEY,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TEXT DEFAULT ''
        )
    """)

    # 每日快照表
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS snapshots (
            id TEXT PRIMARY KEY,
            fund_id TEXT NOT NULL,
            date TEXT NOT NULL,
            safety_cushion REAL,
            recovery_needed REAL,
            today_change REAL DEFAULT 0,
            total_return REAL DEFAULT 0
        )
    """)

    # 插入默认配置（如果不存在）
    cursor.execute(
        "INSERT OR IGNORE INTO config (id, data) VALUES ('default', ?)",
        (json.dumps(DEFAULT_CONFIG, ensure_ascii=False),),
    )

    conn.commit()
    conn.close()


# ==================== 默认配置 ====================

DEFAULT_CONFIG: Dict[str, Any] = {
    "style": "进取型",
    "stopProfitLine": 20,
    "addPositionLine": -15,
    "addPositionMode": "multi",
    "addTiers": [
        {"line": -5, "ratio": 3},
        {"line": -10, "ratio": 5},
        {"line": -15, "ratio": 8},
        {"line": -20, "ratio": 12},
    ],
    "stopProfitRatio": 12,
    "trailingStop": 8,
    "useTrailingStop": True,
    "extremeVolatility": 5,
    "enableStopLoss": True,
    "stopLossLine": -25,
    "stopLossRatio": 50,
    "freeDays": 7,
    "maxPosition": 40,
    "peakReturnRate": {},
}


# ==================== 工具函数 ====================

def gen_id() -> str:
    return uuid.uuid4().hex[:12]


def now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def today_str() -> str:
    return datetime.now().strftime("%Y-%m-%d")
