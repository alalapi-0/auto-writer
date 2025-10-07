"""快速验证多后端 LLM 客户端的占位能力。"""

from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

from autowriter_text.generator.llm_client import generate
from autowriter_text.pipeline.postprocess import ArticleRow

from exporter.common import export_index_csv_json
from exporter.wechat_exporter import export_for_wechat
from exporter.zhihu_exporter import export_for_zhihu


def main() -> None:
    """打印一段占位响应或真实模型输出。"""

    prompt = "请简述 AutoWriter 的设计目标。"
    result = generate(prompt)
    print(result)

    # 验证导出模块可在临时目录落地 1 篇素材包。
    article = ArticleRow(
        id=1,
        title="测试角色 · 测试关键词",
        role_name="测试角色",
        keyword_term="测试关键词",
        content_md="示例正文\n\n- 列表项",  # 结构化 Markdown，确保转换成功。
        created_at="2024-01-01T00:00:00",
        content_hash="demo",
    )
    with TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        wechat_rows = export_for_wechat([article], tmp_path / "wechat")
        zhihu_rows = export_for_zhihu([article], tmp_path / "zhihu")
        export_index_csv_json(tmp_path / "wechat", wechat_rows)
        export_index_csv_json(tmp_path / "zhihu", zhihu_rows)
        wechat_article_dir = next(p for p in (tmp_path / "wechat").iterdir() if p.is_dir())
        zhihu_article_dir = next(p for p in (tmp_path / "zhihu").iterdir() if p.is_dir())
        assert (wechat_article_dir / "paste_wechat.txt").exists()
        assert (zhihu_article_dir / "paste_zhihu.txt").exists()


if __name__ == "__main__":
    main()
