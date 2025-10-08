"""针对导出与打包流程的轻量级冒烟测试。"""

from __future__ import annotations

import zipfile
from pathlib import Path

from autowriter_text.pipeline.postprocess import ArticleRow

from exporter.common import export_index_csv_json
from exporter.packer import bundle_all, zip_dir
from exporter.wechat_exporter import export_for_wechat
from exporter.zhihu_exporter import export_for_zhihu


def _build_article(article_id: int = 1) -> ArticleRow:
    """构造带有简单 Markdown 的文章对象。"""

    return ArticleRow(
        id=article_id,
        title=f"示例标题{article_id}",
        role_name="角色甲",
        keyword_term="关键词乙",
        # 包含 CRLF 以验证打包阶段换行符统一处理。
        content_md="# 章节\r\n\r\n正文行",
        created_at="2024-06-01 00:00:00",
        content_hash="hash-value",
    )


def test_export_and_bundle(tmp_path: Path) -> None:
    """验证导出产物与 ZIP 打包流程的核心路径。"""

    articles = [_build_article()]

    wechat_dir = tmp_path / "wechat"
    wechat_rows = export_for_wechat(articles, wechat_dir)
    export_index_csv_json(wechat_dir, wechat_rows)

    zhihu_dir = tmp_path / "zhihu"
    zhihu_rows = export_for_zhihu(articles, zhihu_dir)
    export_index_csv_json(zhihu_dir, zhihu_rows)

    # 每个平台应生成 1 个文章目录及索引文件。
    wechat_article_dir = next(path for path in wechat_dir.iterdir() if path.is_dir())
    zhihu_article_dir = next(path for path in zhihu_dir.iterdir() if path.is_dir())
    assert (wechat_dir / "index.csv").exists()
    assert (zhihu_dir / "index.json").exists()

    # paste 文件首行标题、次行摘要/正文的结构应符合约定。
    wechat_paste = (wechat_article_dir / "paste_wechat.txt").read_text(encoding="utf-8")
    assert wechat_paste.splitlines()[0] == "示例标题1"
    zhihu_paste = (zhihu_article_dir / "paste_zhihu.txt").read_text(encoding="utf-8")
    assert zhihu_paste.splitlines()[0] == "示例标题1"

    # 压缩后的文本文件应统一为 LF 换行。
    wechat_zip = zip_dir(wechat_dir, tmp_path / "wechat.zip")
    with zipfile.ZipFile(wechat_zip) as zf:
        html_content = zf.read(f"{wechat_article_dir.name}/article.html").decode("utf-8")
        assert "\r" not in html_content

    zhihu_zip = zip_dir(zhihu_dir, tmp_path / "zhihu.zip")
    with zipfile.ZipFile(zhihu_zip) as zf:
        md_content = zf.read(f"{zhihu_article_dir.name}/article.md").decode("utf-8")
        assert "\r" not in md_content

    bundle_path = bundle_all(wechat_dir, zhihu_dir, tmp_path / "bundle.zip")
    with zipfile.ZipFile(bundle_path) as zf:
        names = zf.namelist()
        assert any(name.startswith("wechat/") for name in names)
        assert any(name.startswith("zhihu/") for name in names)
