"""对生成内容进行清洗。"""

from __future__ import annotations

from typing import Mapping


def sanitize(raw_text: str, pair: Mapping[str, str]) -> str:
    """去除多余空白并附带角色上下文。"""

    cleaned = raw_text.strip()
    if not cleaned:
        raise ValueError("生成内容为空")
    header = f"【角色】{pair.get('role_name', '角色')} | 【关键词】{pair.get('keyword_term', '主题')}\n"
    return header + cleaned


__all__ = ["sanitize"]
