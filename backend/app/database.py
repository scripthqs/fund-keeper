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
            fund_code TEXT DEFAULT '',
            fund_shares REAL DEFAULT 0,
            last_nav_update TEXT DEFAULT '',
            initial_principal REAL DEFAULT 0,
            buy_date TEXT DEFAULT '',
            total_buy_amount REAL DEFAULT 0,
            total_sell_amount REAL DEFAULT 0,
            current_market_value REAL DEFAULT 0,
            current_return_rate REAL DEFAULT 0,
            add_tiers TEXT DEFAULT '',
            strategy_type TEXT DEFAULT 'downside',
            pullback_tiers TEXT DEFAULT '',
            max_investment REAL DEFAULT 0,
            stop_profit_line REAL DEFAULT 0,
            stop_loss_line REAL DEFAULT 0,
            stop_profit_ratio REAL DEFAULT 0,
            stop_loss_ratio REAL DEFAULT 0,
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
            snapshot_before TEXT DEFAULT '',
            ai_evaluation TEXT DEFAULT '',
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

    # 增量迁移：为已有数据库添加新列
    migrate_db()


def migrate_db():
    """增量迁移：为已有数据库添加新列"""
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute("ALTER TABLE funds ADD COLUMN strategy_type TEXT DEFAULT 'downside'")
    except sqlite3.OperationalError:
        pass  # 列已存在
    try:
        cursor.execute("ALTER TABLE funds ADD COLUMN pullback_tiers TEXT DEFAULT ''")
    except sqlite3.OperationalError:
        pass  # 列已存在
    conn.commit()
    conn.close()


# ==================== 默认配置 ====================

DEFAULT_CONFIG: Dict[str, Any] = {
    "style": "激进型",
    "stopProfitLine": 30,
    "addPositionLine": -20,
    "addPositionMode": "multi",
    "addTiers": [
        {"line": -8, "ratio": 5},
        {"line": -12, "ratio": 10},
        {"line": -17, "ratio": 18},
        {"line": -22, "ratio": 28},
    ],
    "stopProfitRatio": 10,
    "trailingStop": 15,
    "useTrailingStop": True,
    "extremeVolatility": 8,
    "enableStopLoss": True,
    "stopLossLine": -35,
    "stopLossRatio": 60,
    "freeDays": 7,
    "maxPosition": 50,
    "peakReturnRate": {},
}


# ==================== 工具函数 ====================

def gen_id() -> str:
    return uuid.uuid4().hex[:12]


def now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def today_str() -> str:
    return datetime.now().strftime("%Y-%m-%d")
