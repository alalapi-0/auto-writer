"""基础单元测试示例。"""

from __future__ import annotations

from app.utils.helpers import chunk_items


def test_chunk_items() -> None:
    """验证 chunk_items 函数能够按预期分组。"""

    data = ["a", "b", "c", "d"]  # 准备测试数据
    result = chunk_items(data, size=2)  # 调用函数进行分组
    assert result == [["a", "b"], ["c", "d"]]  # 断言输出符合期望
