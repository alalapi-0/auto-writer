"""Medium 平台草稿箱适配器示例。

真实集成需遵循 Medium 的 OAuth2 / Integration Token 鉴权流程，当前文件
以详尽注释列出调用草稿 API 所需的请求示例。
"""

from __future__ import annotations

from typing import Dict  # 约束文章数据的键值类型

import structlog  # 用于记录占位调用日志

from app.delivery.base import BaseDeliveryAdapter  # 抽象基类

LOGGER = structlog.get_logger()  # 初始化日志器


class MediumDeliveryAdapter(BaseDeliveryAdapter):
    """通过 Medium API 将文章推送至草稿箱的占位实现。"""

    platform_name = "medium"  # 标识平台名称

    def __init__(self, token: str) -> None:
        """保存 Medium API 凭证。"""

        self.token = token  # 存储 Medium API Token，真实场景需用户填写

    def _deliver(self, article: Dict[str, str]) -> None:
        """调用 Medium API 创建草稿。

        真实请求示例（POST https://api.medium.com/v1/users/{userId}/posts）：
        ```json
        {
            "title": "文章标题",
            "contentFormat": "html",
            "content": "<h1>正文</h1>",
            "tags": ["auto-writer"],
            "publishStatus": "draft"
        }
        ```
        请求头需包含 ``Authorization: Bearer <integration_token>``。
        若官方草稿 API 受限，可退化为发布未公开（``publishStatus": "draft"`` 或
        ``"unlisted"``）并在响应中记录 URL 供人工审核。
        """

        LOGGER.info(  # 当前仅输出日志表示已调用
            "medium_deliver_placeholder",
            title=article.get("title"),
        )
        raise NotImplementedError("Medium API 集成尚未实现")  # 提示需要后续开发
