"""通用工具函数集合。"""

from __future__ import annotations

from datetime import datetime
from typing import Iterable, List


def chunk_items(items: Iterable[str], size: int) -> List[List[str]]:
    """按照指定大小切分可迭代对象。"""

    chunk: List[str] = []  # 临时列表存放当前分组
    result: List[List[str]] = []  # 最终结果列表
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
