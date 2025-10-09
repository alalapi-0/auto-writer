"""公众号最小可用适配器：渲染 Markdown/HTML 并落地 outbox。"""  # 模块中文说明
from __future__ import annotations  # 启用未来注解语法

import datetime  # 处理时间戳
import json  # 写入 meta 信息
import os  # 操作文件系统
from typing import Dict  # 类型提示

from app.delivery.types import DeliveryResult  # 引入统一返回类型


def sanitize_filename(text: str) -> str:
    """将标题转换为安全的文件夹名称。"""  # 函数中文文档

    cleaned = "".join(ch for ch in text if ch not in "\\/:*?\"<>|").strip()  # 过滤非法字符
    return cleaned[:80] or "draft"  # 截断长度并提供兜底值


def _ensure_body(article: Dict[str, str]) -> str:
    """获取正文内容，兼容 content/body 字段。"""  # 新增: 帮助函数

    return article.get("body") or article.get("content") or ""  # 优先 body 再 content


def deliver(article: dict, settings) -> DeliveryResult:
    """将文章渲染为公众号草稿制品并返回投递结果。"""  # 函数中文文档

    body = _ensure_body(article)  # 获取正文内容
    title = article.get("title") or "未命名文章"  # 读取标题
    day = datetime.datetime.now().strftime("%Y%m%d")  # 计算日期目录
    base_dir = os.path.join(getattr(settings, "outbox_dir", "./outbox"), "wechat_mp", day)  # 拼接基础路径
    os.makedirs(base_dir, exist_ok=True)  # 创建日期目录
    folder = os.path.join(base_dir, sanitize_filename(title))  # 拼接文章目录
    os.makedirs(folder, exist_ok=True)  # 确保文章目录存在

    md_path = os.path.join(folder, "draft.md")  # Markdown 文件路径
    html_path = os.path.join(folder, "draft.html")  # HTML 文件路径
    meta_path = os.path.join(folder, "meta.json")  # 元数据文件路径

    md_content = f"# {title}\n\n{body}\n"  # 构造 Markdown 内容
    html_lines = [f"<p>{line}</p>" for line in body.splitlines()]  # 将正文按行包裹段落
    html_content = f"<h1>{title}</h1>\n" + "\n".join(html_lines)  # 拼接 HTML 内容

    with open(md_path, "w", encoding="utf-8") as fh:  # 写入 Markdown
        fh.write(md_content)  # 写入文本
    with open(html_path, "w", encoding="utf-8") as fh:  # 写入 HTML
        fh.write(html_content)  # 写入文本

    meta = {
        "role": article.get("role_slug"),  # 角色信息
        "work": article.get("work_slug"),  # 作品信息
        "keyword": article.get("psych_keyword"),  # 心理关键词
        "lang": article.get("lang", "zh"),  # 语言代码
        "created_at": datetime.datetime.now().isoformat(),  # 生成时间
    }  # 构造元数据
    with open(meta_path, "w", encoding="utf-8") as fh:  # 写入元数据
        json.dump(meta, fh, ensure_ascii=False, indent=2)  # 输出 JSON

    payload = {"files": ["draft.md", "draft.html", "meta.json"], "dir": folder}  # 构造 payload
    return DeliveryResult(platform="wechat_mp", status="prepared", out_dir=folder, payload=payload)  # 返回结果
