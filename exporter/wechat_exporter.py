"""将文章导出为微信公众号草稿所需的素材包。"""

from __future__ import annotations

import re
from dataclasses import asdict
from pathlib import Path
from typing import List, Optional

from autowriter_text.pipeline.postprocess import ArticleRow

from .common import ensure_dir, make_digest, md_to_html, write_json, write_text

# 公众号导入的操作提示，写入每篇文章目录便于人工参考。
WECHAT_README = """# 公众号导入步骤\n\n1. 打开 https://mp.weixin.qq.com 草稿箱，新建图文消息。\n2. 复制 `title.txt` 到标题输入框。\n3. 复制 `digest.txt` 到摘要栏（系统已截断至 120 字）。\n4. 打开 `article.html`，整体复制粘贴到正文编辑器（选择源码粘贴更稳定）。\n5. 将 `images/` 目录中的图片手动上传并替换占位。\n6. 对照 `meta.json` 确认角色、关键词、创建时间无误后保存草稿。\n"""


def _slugify(title: str) -> str:
    """根据标题生成目录名，保留中英文并将其它字符替换为下划线。"""

    slug = re.sub(r"[^\w\u4e00-\u9fff]+", "_", title)
    slug = re.sub(r"_+", "_", slug).strip("_")
    return slug or "article"


def export_for_wechat(
    articles: List[ArticleRow],
    out_dir: str | Path,
    default_cover: Optional[str] = None,
) -> List[dict[str, object]]:
    """导出文章到指定目录，并返回索引所需的元数据列表。"""

    export_path = ensure_dir(out_dir)
    rows: List[dict[str, object]] = []
    for idx, article in enumerate(articles, start=1):
        slug = _slugify(article.title)
        article_dir = ensure_dir(export_path / f"{idx:02d}_{slug}")
        digest = make_digest(article.content_md)
        # 逐行注释：写入标题与摘要文本，方便人工直接复制。
        write_text(article_dir / "title.txt", article.title)
        write_text(article_dir / "digest.txt", digest)
        # 保存 Markdown 与 HTML，分别满足编辑器差异化需求。
        write_text(article_dir / "article.md", article.content_md)
        html_body = (article.content_html or "").strip()
        if not html_body:
            html_body = md_to_html(article.content_md)
        write_text(article_dir / "article.html", html_body)
        # 合并粘贴文件：按需求排列标题、摘要与 HTML 正文。
        paste_body = "\n".join([article.title, digest, html_body])
        write_text(article_dir / "paste_wechat.txt", paste_body)
        # 输出导入指南与空图片目录。
        write_text(article_dir / "README_IMPORT.md", WECHAT_README)
        ensure_dir(article_dir / "images")
        meta = {
            "article": asdict(article),
            "digest": digest,
            "default_cover": default_cover,
            "export_dir": str(article_dir),
        }
        write_json(article_dir / "meta.json", meta)
        rows.append(
            {
                "platform": "wechat",
                "article_id": article.id,
                "title": article.title,
                "role": article.role_name,
                "keyword": article.keyword_term,
                "created_at": article.created_at,
                "content_hash": article.content_hash or "",
                "digest": digest,
                "dir": article_dir.name,
            }
        )
    return rows


__all__ = ["export_for_wechat"]
