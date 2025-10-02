"""WordPress 平台草稿箱适配器示例。

重点说明 REST API 请求结构以及鉴权方式，真实实现需使用 HTTPS 并妥善保管凭证。
"""

from __future__ import annotations

from typing import Dict  # 规范文章结构

import structlog  # 输出占位日志

from app.delivery.base import BaseDeliveryAdapter

LOGGER = structlog.get_logger()  # 初始化日志器


class WordPressDeliveryAdapter(BaseDeliveryAdapter):
    """通过 WordPress REST API 创建草稿的占位逻辑。"""

    platform_name = "wordpress"  # 平台名称用于日志区分

    def __init__(self, username: str, password: str) -> None:
        """保存 WordPress 授权信息。"""

        self.username = username  # 存储用户名供 Basic Auth 使用
        self.password = password  # 存储密码，建议后续使用应用专用密码

    def deliver(self, article: Dict[str, str]) -> None:
        """模拟调用 WordPress REST 接口。

        真实请求示例（POST https://example.com/wp-json/wp/v2/posts）：
        ```json
        {
            "title": "文章标题",
            "content": "<p>正文 HTML</p>",
            "status": "draft",
            "categories": [1],
            "tags": [5, 8]
        }
        ```
        鉴权方式通常为 Basic Auth 或 Application Passwords，也可使用 JWT/OAuth。
        若站点启用了 XML-RPC 以外的安全策略，需要在 header 中携带 ``X-WP-Nonce``。
        """

        LOGGER.info(  # 日志提示调用已触发
            "wordpress_deliver_placeholder",
            title=article.get("title"),
        )
        raise NotImplementedError("WordPress API 集成尚未实现")  # 占位异常提示
