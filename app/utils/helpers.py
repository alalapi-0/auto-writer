"""通用工具函数集合。

当前包含分块迭代器与时间工具，后续可扩展更多辅助函数。
"""

from __future__ import annotations

from datetime import datetime  # 提供时间工具
from typing import Iterable, List  # 类型注解，便于理解输入输出


def chunk_items(items: Iterable[str], size: int) -> List[List[str]]:
    """按照指定大小切分可迭代对象。

    参数:
        items: 需要被分组的可迭代对象。
        size: 每组的最大元素数量，必须为正整数。
    返回:
        由多个列表组成的列表，每个子列表长度不超过 ``size``。
    """

    chunk: List[str] = []  # 临时列表存放当前分组
    result: List[List[str]] = []  # 最终结果列表
    if size <= 0:  # 防御式编程，避免无限循环
        raise ValueError("size 必须为正整数")
    for item in items:  # 遍历所有元素
        chunk.append(item)  # 将元素加入当前分组
        if len(chunk) >= size:  # 当分组达到指定数量
            result.append(chunk.copy())  # 将分组副本加入结果
            chunk.clear()  # 清空临时分组
    if chunk:  # 若最后还有残留元素
        result.append(chunk)  # 加入结果列表
    return result  # 返回切分后的二维列表


def utc_now_str() -> str:
    """返回当前 UTC 时间的 ISO 格式字符串。"""

    return datetime.utcnow().isoformat()  # 调用 datetime.utcnow 并转为字符串
