"""示例过滤插件：去除带有强呼吁语句的段落。"""  # 模块说明

from __future__ import annotations  # 启用未来注解

CTA_KEYWORDS = ["赶快", "立即", "立刻", "扫码关注", "分享给朋友"]  # 呼吁关键词列表


def meta() -> dict:  # 插件元数据函数
    """返回插件的元信息供 Dashboard 展示。"""  # 中文说明

    return {"name": "no_call_to_action", "kind": "filters", "version": "0.1.0", "description": "删除带有呼吁词的句子"}  # 返回元数据


def on_after_generate(article: dict) -> dict:  # 钩子函数
    """在文章生成后执行，移除包含呼吁词的段落。"""  # 中文说明

    content = article.get("content", "")  # 获取文章内容
    if not content:  # 若内容为空
        return article  # 直接返回
    lines = []  # 存放保留段落
    for line in content.splitlines():  # 遍历每一行
        if any(keyword in line for keyword in CTA_KEYWORDS):  # 检测呼吁词
            continue  # 跳过该段落
        lines.append(line)  # 保留段落
    article["content"] = "\n".join(lines)  # 重新拼接内容
    return article  # 返回处理后的文章
