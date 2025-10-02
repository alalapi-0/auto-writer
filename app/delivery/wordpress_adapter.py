"""WordPress 平台草稿箱适配器示例。"""

from __future__ import annotations

from typing import Dict

import structlog

from app.delivery.base import BaseDeliveryAdapter

LOGGER = structlog.get_logger()


class WordPressDeliveryAdapter(BaseDeliveryAdapter):
    """通过 WordPress REST API 创建草稿的占位逻辑。"""

    platform_name = "wordpress"  # 平台名称用于日志区分

    def __init__(self, username: str, password: str) -> None:
        self.username = username  # 存储用户名供 Basic Auth 使用
        self.password = password  # 存储密码，建议后续使用应用专用密码

    def deliver(self, article: Dict[str, str]) -> None:
        """模拟调用 WordPress REST 接口。"""

        # 实际步骤示例：
        # 1. 使用 requests 库向 /wp-json/wp/v2/posts 发起 POST 请求。
        # 2. 通过 HTTP Basic Auth 提供用户名与应用密码，或使用 OAuth2 token。
        # 3. 在请求体中设置 "status": "draft" 并传入 title、content 等字段。
        # 4. 检查响应状态码，记录成功或错误信息。
        LOGGER.info("wordpress_deliver_placeholder", title=article.get("title"))  # 日志提示调用已触发
        raise NotImplementedError("WordPress API 集成尚未实现")  # 占位异常提示
