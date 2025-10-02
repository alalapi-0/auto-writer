"""文章生成器模块，封装与大语言模型交互逻辑。"""

from __future__ import annotations

from typing import Dict

import structlog

from config.settings import BASE_DIR

LOGGER = structlog.get_logger()
PROMPT_PATH = BASE_DIR / "app" / "generator" / "prompts" / "default_prompt.txt"  # 默认提示词模板路径


class ArticleGenerator:
    """使用占位实现模拟文章生成行为。"""

    def __init__(self, api_key: str) -> None:
        self.api_key = api_key  # 存储 API Key，真实实现中用于鉴权

    def _load_prompt_template(self) -> str:
        """读取默认提示词模板。"""

        template = PROMPT_PATH.read_text(encoding="utf-8")  # 读取模板文件内容
        LOGGER.debug("prompt_loaded", template_length=len(template))  # 输出模板长度用于调试
        return template

    def generate_article(self, topic: str) -> Dict[str, str]:
        """根据主题生成文章草稿。"""

        template = self._load_prompt_template()  # 加载提示词模板
        article_body = template.replace("{{topic}}", topic)  # 使用主题填充模板占位符
        # 真实场景应调用 LLM API，例如 OpenAI ChatCompletion；此处返回模拟数据
        LOGGER.info("article_generated", topic=topic)  # 记录生成完成日志
        return {
            "title": f"{topic} 的深度洞察",  # 模拟生成文章标题
            "content": article_body,  # 模拟生成文章内容
            "keywords": [topic, "自动写作"],  # 假定关键词列表
        }
