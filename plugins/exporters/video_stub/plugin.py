"""示例导出插件：将文章信息写入视频待处理目录。"""  # 模块说明

from __future__ import annotations  # 启用未来注解语法

from pathlib import Path  # 处理路径

OUTBOX = Path("outbox/video_todo")  # 输出目录


def meta() -> dict:  # 插件元数据
    """返回插件元信息，便于 Dashboard 显示状态。"""  # 中文说明

    return {"name": "video_stub", "kind": "exporters", "version": "0.1.0", "description": "生成视频任务占位文件"}  # 返回元数据


def on_after_publish(result: dict, platform: str) -> None:  # 钩子函数
    """在文章发布后调用，将标题与摘要写入占位文件。"""  # 中文说明

    OUTBOX.mkdir(parents=True, exist_ok=True)  # 确保目录存在
    title = result.get("title", "untitled")  # 获取标题
    summary = result.get("summary", "")  # 获取摘要
    filename = OUTBOX / f"{platform}_{title}.txt"  # 构造文件名
    content = f"平台: {platform}\n标题: {title}\n摘要: {summary}\n"  # 构造写入内容
    filename.write_text(content, encoding="utf-8")  # 写入文件
