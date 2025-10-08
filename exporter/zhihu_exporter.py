"""导出知乎文章所需的素材文件。"""

from __future__ import annotations

import re
from dataclasses import asdict
from pathlib import Path
from typing import List

from autowriter_text.pipeline.postprocess import ArticleRow

from .common import ensure_dir, md_to_html, normalize_title, write_json, write_text

ZHIHU_README = """# 知乎导入步骤\n\n1. 打开知乎写作页面，选择文章创作。\n2. 新建草稿后，将 `title.txt` 内容粘贴到标题。\n3. 打开 `article.md`，复制全文（推荐使用 Markdown 编辑器保持格式）。\n4. 在知乎编辑器中选择“Markdown 粘贴”或使用 `Ctrl+Shift+V` 粘贴纯文本，再逐段校对。\n5. 如需插图，请按 `images/` 文件名顺序手动上传。\n6. 校验 `meta.json` 中的角色、关键词与生成时间后发布或保存草稿。\n"""


def _slugify(title: str) -> str:
    """生成知乎导出目录名，与公众号保持一致策略。"""

    slug = re.sub(r"[^\w\u4e00-\u9fff]+", "_", title)
    slug = re.sub(r"_+", "_", slug).strip("_")
    return slug or "article"


def export_for_zhihu(articles: List[ArticleRow], out_dir: str | Path) -> List[dict[str, object]]:
    """导出知乎草稿文件并返回索引列表。"""

    export_path = ensure_dir(out_dir)
    rows: List[dict[str, object]] = []
    for idx, article in enumerate(articles, start=1):
        slug = _slugify(article.title)
        article_dir = ensure_dir(export_path / f"{idx:02d}_{slug}")
        title_text = normalize_title(article.title)
        write_text(article_dir / "title.txt", title_text)
        write_text(article_dir / "article.md", article.content_md)
        html_body = (article.content_html or "").strip()
        if not html_body:
            html_body = md_to_html(article.content_md)
        write_text(article_dir / "article.html", html_body)
        # 合并粘贴文件：首行标题，其余为 Markdown 正文，方便单次复制。
        paste_body = "\n".join([title_text, article.content_md])
        write_text(article_dir / "paste_zhihu.txt", paste_body)
        write_text(article_dir / "README_IMPORT.md", ZHIHU_README)
        ensure_dir(article_dir / "images")
        meta = {
            "article": asdict(article),
            "export_dir": str(article_dir),
        }
        write_json(article_dir / "meta.json", meta)
        rows.append(
            {
                "platform": "zhihu",
                "article_id": article.id,
                "title": title_text,
                "role": article.role_name,
                "keyword": article.keyword_term,
                "created_at": article.created_at,
                "content_hash": article.content_hash or "",
                "dir": article_dir.name,
            }
        )
    return rows


__all__ = ["export_for_zhihu"]
