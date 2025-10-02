"""应用主入口，负责 orchestrate 文章生成与投递流程。"""

from __future__ import annotations

import structlog

from config.settings import settings  # 导入全局配置，获取 API Key 与数据库信息
from app.generator.article_generator import ArticleGenerator  # 引入文章生成器
from app.delivery.medium_adapter import MediumDeliveryAdapter  # Medium 平台适配器
from app.delivery.wordpress_adapter import WordPressDeliveryAdapter  # WordPress 平台适配器
from app.delivery.wechat_mp_adapter import WeChatMPDeliveryAdapter  # 微信公众号适配器
from app.dedup.deduplicator import ArticleDeduplicator  # 去重服务
from app.db.migrate import init_database  # 初始化数据库函数

LOGGER = structlog.get_logger()  # 获取结构化日志记录器


def main() -> None:
    """执行文章生成与多平台投递的核心流程。"""

    init_database()  # 初始化数据库，确保数据表存在
    generator = ArticleGenerator(api_key=settings.openai_api_key)  # 创建文章生成器实例，传入 API Key
    deduplicator = ArticleDeduplicator()  # 构建去重组件，负责检查关键词与主题

    article_payload = generator.generate_article(topic="AI 技术趋势")  # 调用生成器生成文章草稿
    if not deduplicator.is_unique(article_payload):  # 判断文章是否重复
        LOGGER.info("article_skipped", reason="duplicate")  # 记录日志说明跳过原因
        return

    adapters = [
        MediumDeliveryAdapter(token=settings.openai_api_key),  # 伪使用 OpenAI Key 占位，真实场景应为各平台凭证
        WordPressDeliveryAdapter(
            username="",
            password="",
        ),
        WeChatMPDeliveryAdapter(cookies=""),
    ]

    for adapter in adapters:  # 遍历每个平台适配器
        try:
            adapter.deliver(article_payload)  # 调用适配器的投递方法
            LOGGER.info("delivery_success", platform=adapter.platform_name)  # 输出投递成功日志
        except NotImplementedError:
            LOGGER.warning("delivery_not_implemented", platform=adapter.platform_name)  # 提示接口尚未实现
        except Exception as exc:  # 捕获其他异常
            LOGGER.error("delivery_failed", platform=adapter.platform_name, error=str(exc))  # 输出错误信息


if __name__ == "__main__":  # 当脚本直接执行时
    main()  # 调用主函数
