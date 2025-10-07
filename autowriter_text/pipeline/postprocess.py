"""导出阶段使用的查询函数与数据结构。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import List

from autowriter_text.db import ensure_schema, get_connection
from autowriter_text.logging import logger


@dataclass(slots=True)
class ArticleRow:
    """简化后的文章记录，供导出模块消费。"""

    id: int
    title: str
    role_name: str
    keyword_term: str
    content_md: str
    created_at: str
    content_hash: str | None


def collect_articles_for_date(date_str: str) -> List[ArticleRow]:
    """按日期收集最多 5 篇文章，保留导出所需字段。"""

    # 验证日期格式，捕捉输入错误。
    datetime.strptime(date_str, "%Y-%m-%d")
    with get_connection() as conn:
        ensure_schema(conn)
        cursor = conn.execute(
            """
            SELECT
                a.id,
                a.title,
                r.name AS role_name,
                k.term AS keyword_term,
                a.content AS content_md,
                COALESCE(a.created_at, '') AS created_at,
                a.content_hash
            FROM articles AS a
            JOIN roles AS r ON r.id = a.role_id
            JOIN keywords AS k ON k.id = a.keyword_id
            WHERE date(a.created_at) = ?
            ORDER BY a.created_at ASC, a.id ASC
            LIMIT 5
            """,
            (date_str,),
        )
        rows = [
            ArticleRow(
                id=row["id"],
                title=row["title"],
                role_name=row["role_name"],
                keyword_term=row["keyword_term"],
                content_md=row["content_md"],
                created_at=row["created_at"],
                content_hash=row["content_hash"],
            )
            for row in cursor.fetchall()
        ]
    logger.info("收集文章 %s 篇用于导出", len(rows))
    return rows


__all__ = ["ArticleRow", "collect_articles_for_date"]
