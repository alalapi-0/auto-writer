"""平台投递适配器抽象基类。

所有内容平台适配器都应继承此基类，并实现 ``deliver`` 方法。
"""

from __future__ import annotations

from abc import ABC, abstractmethod  # 用于定义抽象基类与抽象方法
from typing import Dict


class BaseDeliveryAdapter(ABC):
    """定义适配器公共接口。

    属性:
        platform_name: 子类覆盖该属性以在日志中标识具体平台。
    """

    platform_name: str = "unknown"  # 平台名称，子类需覆盖

    @abstractmethod
    def deliver(self, article: Dict[str, str]) -> None:
        """将文章投递到目标平台草稿箱。

        参数:
            article: 包含标题、正文、关键词等字段的文章数据。

        异常:
            子类可抛出 NotImplementedError 或实际 API 异常，交由调用方处理。
        """

        raise NotImplementedError  # 子类必须实现具体逻辑
