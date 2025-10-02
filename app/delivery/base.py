"""平台投递适配器抽象基类。"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Dict


class BaseDeliveryAdapter(ABC):
    """定义适配器公共接口。"""

    platform_name: str = "unknown"  # 平台名称，子类需覆盖

    @abstractmethod
    def deliver(self, article: Dict[str, str]) -> None:
        """将文章投递到目标平台草稿箱。"""

        raise NotImplementedError  # 子类必须实现具体逻辑
