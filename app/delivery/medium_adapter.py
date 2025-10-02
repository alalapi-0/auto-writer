"""Medium 平台草稿箱适配器示例。"""

from __future__ import annotations

from typing import Dict

import structlog

from app.delivery.base import BaseDeliveryAdapter

LOGGER = structlog.get_logger()


class MediumDeliveryAdapter(BaseDeliveryAdapter):
    """通过 Medium API 将文章推送至草稿箱的占位实现。"""

    platform_name = "medium"  # 标识平台名称

    def __init__(self, token: str) -> None:
        self.token = token  # 存储 Medium API Token，真实场景需用户填写

    def deliver(self, article: Dict[str, str]) -> None:
        """调用 Medium API 创建草稿。"""

        # 真实实现步骤示例：
        # 1. 构造 HTTPS 请求头，包含 Authorization Bearer token。
        # 2. 调用 Medium 提供的 /users/{id}/posts 接口，并在 payload 中设置 "publishStatus": "draft"。
        # 3. 处理返回状态码，捕获异常并记录详细日志。
        LOGGER.info("medium_deliver_placeholder", title=article.get("title"))  # 当前仅输出日志表示已调用
        raise NotImplementedError("Medium API 集成尚未实现")  # 提示需要后续开发
