"""知乎最小可用适配器：生成 Markdown 与元数据。"""  # 模块中文说明
from __future__ import annotations  # 启用未来注解语法

import datetime  # 处理时间
import json  # 序列化元数据
import os  # 操作文件

from app.delivery.types import DeliveryResult  # 引入统一返回类型
from app.delivery.wechat_mp_adapter import _ensure_body, sanitize_filename  # 复用辅助函数


def deliver(article: dict, settings) -> DeliveryResult:
    """将文章转换为知乎草稿制品并返回结果。"""  # 函数中文文档

    body = _ensure_body(article)  # 获取正文
    title = article.get("title") or "未命名文章"  # 读取标题
    day = datetime.datetime.now().strftime("%Y%m%d")  # 生成日期目录
    base_dir = os.path.join(getattr(settings, "outbox_dir", "./outbox"), "zhihu", day)  # 计算基础路径
    os.makedirs(base_dir, exist_ok=True)  # 创建日期目录
    folder = os.path.join(base_dir, sanitize_filename(title))  # 拼接文章目录
    os.makedirs(folder, exist_ok=True)  # 确保文章目录存在

    md_path = os.path.join(folder, "draft.md")  # Markdown 文件路径
    meta_path = os.path.join(folder, "meta.json")  # 元数据路径

    md_content = f"# {title}\n\n{body}\n"  # 构造 Markdown 正文
    with open(md_path, "w", encoding="utf-8") as fh:  # 写入 Markdown
        fh.write(md_content)  # 写入文本

    meta = {
        "role": article.get("role_slug"),  # 角色信息
        "work": article.get("work_slug"),  # 作品信息
        "keyword": article.get("psych_keyword"),  # 心理关键词
        "lang": article.get("lang", "zh"),  # 语言代码
        "created_at": datetime.datetime.now().isoformat(),  # 生成时间
    }  # 构造元数据
    with open(meta_path, "w", encoding="utf-8") as fh:  # 写入元数据
        json.dump(meta, fh, ensure_ascii=False, indent=2)  # 输出 JSON

    payload = {"files": ["draft.md", "meta.json"], "dir": folder}  # 构造 payload
    return DeliveryResult(platform="zhihu", status="prepared", out_dir=folder, payload=payload)  # 返回结果
