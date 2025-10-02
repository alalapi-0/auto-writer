"""文章去重逻辑实现。"""

from __future__ import annotations

from typing import Dict

from sqlalchemy import select

from app.db.migrate import SessionLocal
from app.db.models import Article, Keyword


class ArticleDeduplicator:
    """根据关键词与标题进行重复检查。"""

    def __init__(self) -> None:
        self.session = SessionLocal()  # 创建数据库会话，用于查询历史记录

    def is_unique(self, article: Dict[str, str]) -> bool:
        """检查文章是否为新内容。"""

        title = article.get("title", "")  # 读取标题用于对比
        keyword_list = article.get("keywords", [])  # 读取关键词列表

        existing_article = self.session.execute(
            select(Article).where(Article.title == title)
        ).scalar_one_or_none()  # 查询标题是否已存在
        if existing_article:  # 若已有相同标题
            return False  # 直接判定为重复

        if not keyword_list:  # 若无关键词则无法判断
            return True  # 默认视为新内容

        existing_keyword = self.session.execute(
            select(Keyword).where(Keyword.keyword.in_(keyword_list))
        ).scalar_one_or_none()  # 查询是否存在相同关键词
        return existing_keyword is None  # 若不存在相同关键词则视为唯一
