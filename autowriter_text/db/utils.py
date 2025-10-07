"""SQLite 工具函数。"""

from __future__ import annotations

import sqlite3  # 直接使用内置 sqlite3
from datetime import datetime
from pathlib import Path

from autowriter_text.logging import logger

from autowriter_text.configuration import load_config

SCHEMA_PATH = Path(__file__).resolve().parent / "schema.sql"


def get_connection() -> sqlite3.Connection:
    """返回开启行工厂的数据库连接。"""

    config = load_config()
    db_path = Path(config.database_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def ensure_schema(conn: sqlite3.Connection) -> None:
    """确保 schema.sql 已应用。"""

    script = SCHEMA_PATH.read_text(encoding="utf-8")
    conn.executescript(script)
    conn.commit()


def ensure_pair_usage_scope(conn: sqlite3.Connection, scope: str) -> None:
    """根据配置切换 pair_usage 的唯一索引。"""

    if scope == "global":
        conn.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_pair_usage_role_keyword_global"
            " ON pair_usage(role_id, keyword_id)"
        )
        logger.debug("已启用全局唯一索引 idx_pair_usage_role_keyword_global")
    else:
        conn.execute("DROP INDEX IF EXISTS idx_pair_usage_role_keyword_global")
        logger.debug("已关闭全局唯一索引，交由逻辑层控制日内去重")
    conn.commit()


def record_usage(
    conn: sqlite3.Connection,
    role_id: int,
    keyword_id: int,
    status: str,
    message: str,
    success: bool,
) -> None:
    """记录 usage_log 并在成功时写入 pair_usage。"""

    now = datetime.utcnow().isoformat()
    conn.execute(
        "INSERT INTO usage_log(role_id, keyword_id, status, message, logged_at) VALUES(?,?,?,?,?)",
        (role_id, keyword_id, status, message, now),
    )
    if success:
        conn.execute(
            "INSERT INTO pair_usage(role_id, keyword_id, used_at) VALUES(?,?,?)",
            (role_id, keyword_id, now),
        )
    conn.commit()

