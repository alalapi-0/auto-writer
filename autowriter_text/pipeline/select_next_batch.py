"""根据去重策略选择下一批 (role, keyword) 组合。"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from typing import Any

from autowriter_text.logging import logger

from autowriter_text.configuration import load_config
from autowriter_text.db import ensure_pair_usage_scope, ensure_schema, get_connection


def _available_pairs(scope: str) -> str:
    """返回根据 scope 过滤 pair_usage 的 SQL。"""

    if scope == "global":
        return (
            "SELECT r.id AS role_id, r.name AS role_name, r.work_title, r.voice, "
            "k.id AS keyword_id, k.term AS keyword_term "
            "FROM roles AS r CROSS JOIN keywords AS k "
            "LEFT JOIN pair_usage AS u ON u.role_id = r.id AND u.keyword_id = k.id "
            "WHERE u.id IS NULL ORDER BY r.id, k.id LIMIT :limit"
        )
    return (
        "SELECT r.id AS role_id, r.name AS role_name, r.work_title, r.voice, "
        "k.id AS keyword_id, k.term AS keyword_term "
        "FROM roles AS r CROSS JOIN keywords AS k "
        "LEFT JOIN pair_usage AS u ON u.role_id = r.id AND u.keyword_id = k.id "
        "AND DATE(u.used_at) = :today "
        "WHERE u.id IS NULL ORDER BY r.id, k.id LIMIT :limit"
    )


def select_next_batch(conn: sqlite3.Connection | None = None) -> list[dict[str, Any]]:
    """选取下一批组合。"""

    config = load_config()
    own_connection = conn is None
    if own_connection:
        conn = get_connection()
    assert conn is not None
    try:
        ensure_schema(conn)
        ensure_pair_usage_scope(conn, config.dedup.scope)
        today_iso = datetime.now(timezone.utc).date().isoformat()
        sql = _available_pairs(config.dedup.scope)
        params = {"limit": config.batch.count, "today": today_iso}
        cursor = conn.execute(sql, params)
        rows = [dict(row) for row in cursor.fetchall()]
        if len(rows) < config.batch.count:
            logger.warning(
                "仅找到 %s 条可用组合，低于配置的批次数 %s",
                len(rows),
                config.batch.count,
            )
        return rows
    finally:
        if own_connection and conn is not None:
            conn.close()


__all__ = ["select_next_batch"]
