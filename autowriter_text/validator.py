"""验证生成内容满足最低要求。"""

from __future__ import annotations

from typing import Mapping


MIN_LENGTH = 400


def validate(text: str, pair: Mapping[str, str]) -> None:
    """若验证失败则抛出 ValueError。"""

    if len(text) < MIN_LENGTH:
        raise ValueError(
            f"文章长度不足: {len(text)} < {MIN_LENGTH} (role={pair.get('role_name')}, keyword={pair.get('keyword_term')})"
        )


__all__ = ["validate", "MIN_LENGTH"]
