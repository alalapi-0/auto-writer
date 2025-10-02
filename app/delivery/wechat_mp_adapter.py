"""微信公众号草稿接口适配器说明。"""

from __future__ import annotations

from typing import Dict

import structlog

from app.delivery.base import BaseDeliveryAdapter

LOGGER = structlog.get_logger()


class WeChatMPDeliveryAdapter(BaseDeliveryAdapter):
    """通过微信公众号平台管理端创建草稿的占位实现。"""

    platform_name = "wechat_mp"  # 平台名称

    def __init__(self, cookies: str) -> None:
        self.cookies = cookies  # 存储登录 Cookie，真实使用需从浏览器导出或自动登录

    def deliver(self, article: Dict[str, str]) -> None:
        """模拟微信公众号草稿创建流程。"""

        # 真实流程说明：
        # 1. 通过公众号后台登录获取 session，或调用开放平台接口获取 access_token。
        # 2. 若使用 Web 端接口，需要携带 cookies 和必要的 XSRF token，向 /cgi-bin/operate_appmsg 提交 POST 请求。
        # 3. 上传封面图与正文时需先调用素材上传接口，返回 media_id 再写入草稿。
        # 4. 接口返回成功状态后记录草稿 ID，以便后续发布或编辑。
        LOGGER.info("wechat_mp_deliver_placeholder", title=article.get("title"))  # 当前仅记录日志
        raise NotImplementedError("微信公众平台 API 集成尚未实现")  # 提醒需要开发
