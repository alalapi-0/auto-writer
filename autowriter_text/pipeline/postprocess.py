"""导出阶段使用的查询函数与数据结构。"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List

from autowriter_text.db import ensure_schema, get_connection
from autowriter_text.logging import logger


try:  # 优先使用 markdown-it 渲染 HTML。
    from markdown_it import MarkdownIt
except ImportError:  # pragma: no cover - 允许在最小依赖环境运行
    MarkdownIt = None  # type: ignore[assignment]
try:
    import markdown2
except ImportError:  # pragma: no cover
    markdown2 = None  # type: ignore[assignment]

_MD = MarkdownIt() if MarkdownIt is not None else None


@dataclass(slots=True)
class ArticleRow:
    """简化后的文章记录，供导出模块消费。"""

    id: int
    title: str
    role_name: str
    keyword_term: str
    content_md: str
    content_html: str = ""
    created_at: str = ""
    content_hash: str | None = None
    export_dirs: Dict[str, str] = field(default_factory=dict)


def _md_to_html(md_text: str) -> str:
    """将 Markdown 文本转换为 HTML，用于公众号粘贴。"""

    if _MD is not None:
        return _MD.render(md_text)
    if markdown2 is not None:
        return markdown2.markdown(md_text)
    escaped = md_text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return "<p>" + escaped.replace("\n\n", "</p><p>").replace("\n", "<br />") + "</p>"


def _load_export_dirs(date_str: str) -> Dict[str, Dict[int, Path]]:
    """从导出目录读取 meta.json，建立文章 ID 到目录的映射。"""

    root = Path("exports")
    mapping: Dict[str, Dict[int, Path]] = {"wechat": {}, "zhihu": {}}
    for platform in mapping.keys():
        base = root / platform / date_str
        if not base.exists():
            continue
        for child in base.iterdir():
            if not child.is_dir():
                continue
            meta_path = child / "meta.json"
            if not meta_path.exists():
                continue
            try:
                data = json.loads(meta_path.read_text(encoding="utf-8"))
            except Exception:  # pragma: no cover - meta 格式异常时忽略
                continue
            article = data.get("article", {})
            article_id = article.get("id")
            if isinstance(article_id, int):
                mapping[platform][article_id] = child
    return mapping


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
        db_rows = cursor.fetchall()
    export_dirs = _load_export_dirs(date_str)
    rows: List[ArticleRow] = []
    for row in db_rows:
        article_id = row["id"]
        platform_dirs: Dict[str, str] = {}
        html_body = ""
        for platform, platform_map in export_dirs.items():
            path = platform_map.get(article_id)
            if path is None:
                continue
            platform_dirs[platform] = str(path)
            html_file = path / "article.html"
            if not html_body and html_file.exists():
                html_body = html_file.read_text(encoding="utf-8")
        if not html_body:
            html_body = _md_to_html(row["content_md"])
        rows.append(
            ArticleRow(
                id=article_id,
                title=row["title"],
                role_name=row["role_name"],
                keyword_term=row["keyword_term"],
                content_md=row["content_md"],
                content_html=html_body,
                created_at=row["created_at"],
                content_hash=row["content_hash"],
                export_dirs=platform_dirs,
            )
        )
    logger.info("收集文章 %s 篇用于导出", len(rows))
    return rows


__all__ = ["ArticleRow", "collect_articles_for_date"]
