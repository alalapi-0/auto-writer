"""导出流程的通用工具函数集合。"""

from __future__ import annotations

import csv
import json
import re
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Iterable, Sequence

try:  # 优先使用 markdown-it-py，若未安装则回退。
    from markdown_it import MarkdownIt
except ImportError:  # pragma: no cover - 允许按需降级
    MarkdownIt = None  # type: ignore[assignment]
try:  # 备用选项：markdown2 体积小、易于安装。
    import markdown2
except ImportError:  # pragma: no cover
    markdown2 = None  # type: ignore[assignment]

# 初始化 Markdown 渲染器；若依赖缺失则延迟在 md_to_html 中处理。
_MD = MarkdownIt() if MarkdownIt is not None else None


def ensure_dir(path: str | Path) -> Path:
    """确保目录存在并返回 Path 对象。"""

    path_obj = Path(path)
    # parents=True 递归创建目录，exist_ok 避免目录已存在时报错。
    path_obj.mkdir(parents=True, exist_ok=True)
    return path_obj


def md_to_html(md_text: str) -> str:
    """将 Markdown 文本转换为 HTML。"""

    if _MD is not None:
        # MarkdownIt 会自动处理段落、列表、标题等，适合复制到富文本编辑器。
        return _MD.render(md_text)
    if markdown2 is not None:
        return markdown2.markdown(md_text)
    # 若两种解析器均不可用，退化为用 <br> 处理换行，确保不会阻塞导出。
    escaped = md_text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return "<p>" + escaped.replace("\n\n", "</p><p>").replace("\n", "<br />") + "</p>"


def normalize_title(title: str) -> str:
    """对标题做基本清洗，避免前后空白与重复标点。"""

    cleaned = title.strip()  # 去除首尾空白字符。
    cleaned = re.sub(r"[\s\u3000]+", " ", cleaned)  # 将多余空白压缩成单个空格。
    cleaned = re.sub(r"([，。！？,.!?；;])\1+", r"\1", cleaned)  # 重复标点合并为一个。
    cleaned = cleaned.rstrip("，。！？,.!?；;:：")  # 移除末尾多余标点。
    return cleaned


def short_digest(text: str, max_cn: int = 120) -> str:
    """截断正文用于摘要，避免切断中文标点。"""

    corpus = text.replace("\r", "").replace("\n", "")  # 去除换行符。
    corpus = re.sub(r"\s+", "", corpus)  # 删除内部空白，保留连续文字。
    if len(corpus) <= max_cn:
        return corpus  # 长度不超过限制直接返回。
    snippet = corpus[:max_cn]  # 先切片到指定长度。
    while snippet and snippet[-1] in "，。；！？、：":
        snippet = snippet[:-1]  # 如果结尾是中文标点则继续回退。
    return snippet or corpus[:max_cn]  # 全部回退后仍为空则返回原切片。


def make_digest(text: str, max_len_cn: int = 120) -> str:
    """截取正文前 max_len_cn 个字符作为公众号摘要。"""

    lines = []
    for raw_line in text.replace("\r", "").split("\n"):
        line = raw_line.strip()  # 移除行首尾空白。
        if not line:
            continue  # 跳过空行。
        if line.startswith("【角色】"):
            continue  # 角色说明不进入摘要。
        if re.match(r"^(欢迎|扫码|关注|喜欢|记得)", line):
            continue  # 常见口号类文案直接丢弃。
        lines.append(line)
    merged = "".join(lines)  # 拼接为连续文本供后续截断。
    return merged[: max_len_cn * 2]  # 预裁剪到两倍长度，最终由 short_digest 控制。


def write_text(path: str | Path, content: str) -> None:
    """以 UTF-8 写入纯文本文件。"""

    path_obj = Path(path)
    ensure_dir(path_obj.parent)
    path_obj.write_text(content, encoding="utf-8")


def write_json(path: str | Path, data: object) -> None:
    """将数据以 JSON 格式写入文件，自动处理 dataclass。"""

    path_obj = Path(path)
    ensure_dir(path_obj.parent)
    if is_dataclass(data):
        payload = asdict(data)
    else:
        payload = data
    path_obj.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def export_index_csv_json(export_dir: str | Path, rows: Sequence[dict[str, object]]) -> None:
    """在导出目录生成 index.csv 与 index.json，方便人工检索。"""

    export_path = ensure_dir(export_dir)
    if not rows:
        return
    # 写入 JSON，保留所有字段。
    write_json(export_path / "index.json", list(rows))
    # 写入 CSV 时按 keys 顺序输出，方便使用表格软件查看。
    fieldnames: Iterable[str] = rows[0].keys()
    csv_path = export_path / "index.csv"
    with csv_path.open("w", encoding="utf-8", newline="") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


__all__ = [
    "ensure_dir",
    "export_index_csv_json",
    "make_digest",
    "md_to_html",
    "normalize_title",
    "short_digest",
    "write_json",
    "write_text",
]
