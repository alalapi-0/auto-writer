"""构建文章生成 Prompt。"""

from __future__ import annotations

from typing import Mapping


def build_prompt(pair: Mapping[str, str]) -> str:
    """根据角色与关键词信息生成 Prompt。"""

    role_name = pair.get("role_name", "角色")
    work_title = pair.get("work_title") or "作品"
    keyword = pair.get("keyword_term", "主题")
    voice = pair.get("voice") or "专业影评人"
    return (
        f"你是一名{voice}，请围绕《{work_title}》中的角色“{role_name}”撰写一篇"
        f"主题为“{keyword}”的深度文章。\n"
        "文章要求：\n"
        "1. 采用引言-正文-结尾结构，字数不少于 1200 字。\n"
        "2. 在正文中提供至少三个分段，并结合心理描写、情节推演与现实类比。\n"
        "3. 保持语气稳重、具备洞察力，同时给出可执行的建议或启示。\n"
        "4. 全文使用中文输出，不要包含额外的提示说明。\n"
    )


__all__ = ["build_prompt"]
