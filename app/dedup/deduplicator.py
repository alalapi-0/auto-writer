"""文章去重逻辑实现。

该模块实现“关键词集合 + 历史表扫描”的最小可用去重策略，并在注释中标注
后续可扩展语义向量（SimHash/MinHash/Embedding）能力的接口。
"""

from __future__ import annotations

from typing import Dict, Iterable, Set  # 提供类型标注以增强可读性

from sqlalchemy import Select, func, select  # 导入 SQL 构造器
from sqlalchemy.orm import Session

from app.db.migrate import SessionLocal  # Session 工厂，生成数据库会话
from app.db.models import ArticleDraft, Keyword  # ORM 模型，用于查询历史记录


class ArticleDeduplicator:
    """根据关键词与标题进行重复检查的最小实现。"""

    def __init__(self) -> None:
        """初始化去重服务并缓存 Session 工厂。"""

        self.session_factory = SessionLocal  # 保存 Session 工厂以按需创建连接

    def _normalize_keywords(self, keywords: Iterable[str]) -> Set[str]:
        """将传入关键词统一为去重后的集合。

        参数:
            keywords: 任意可迭代的关键词列表。
        返回:
            经过去重与大小写归一化后的集合。
        """

        return {keyword.strip().lower() for keyword in keywords if keyword.strip()}  # 去除空白并统一大小写

    def _fetch_existing_keywords(self, session: Session, keywords: Set[str]) -> Set[str]:
        """查询数据库中与给定集合重叠的关键词。

        参数:
            session: 打开的 SQLAlchemy Session。
            keywords: 已归一化的关键词集合。
        返回:
            数据库中存在的关键词集合，用于与当前文章比对。
        """

        if not keywords:  # 若集合为空则直接返回空集
            return set()
        keyword_stmt: Select[tuple[str]] = select(  # 构造查询语句
            Keyword.keyword
        ).where(
            Keyword.keyword.in_(keywords)
        )
        rows = session.execute(keyword_stmt).scalars().all()  # 执行查询并提取所有关键字字符串
        return set(rows)  # 转换为集合便于集合运算

    def _is_title_duplicate(self, session: Session, title: str) -> bool:
        """判断标题是否在历史表中已存在。"""

        if not title:  # 空标题直接视为不重复，由调用方决定是否允许
            return False
        title_stmt: Select[tuple[int]] = select(func.count(ArticleDraft.id)).where(  # 构造计数查询
            ArticleDraft.title == title
        )
        count = session.execute(title_stmt).scalar_one()  # 执行查询并取计数
        return count > 0  # 大于零表示存在重复标题

    def is_unique(self, article: Dict[str, str]) -> bool:
        """检查文章是否为新内容。

        参数:
            article: 包含标题、正文与关键词列表的字典。
        返回:
            True 表示未检测到重复，可继续生成/投递。
        """

        title = article.get("title", "")  # 读取标题用于对比
        keyword_list = article.get("keywords", [])  # 读取关键词列表
        normalized_keywords = self._normalize_keywords(keyword_list)  # 归一化关键词集合

        with self.session_factory() as session:  # 打开数据库会话，并确保自动关闭
            if self._is_title_duplicate(session, title):  # 首先基于标题快速判重
                return False  # 标题已存在直接视为重复

            overlapping_keywords = self._fetch_existing_keywords(  # 查询关键词重叠情况
                session, normalized_keywords
            )
            if overlapping_keywords:  # 若存在关键词交集
                # TODO: 在后续版本中，可在此结合关键词权重或文章摘要实现更精细的重复判定。
                return False

        return True  # 无标题冲突且关键词未命中，则视为新内容

    # TODO: 提供 register_article 接口，在文章投递成功后写入关键词与摘要，便于语义去重。
