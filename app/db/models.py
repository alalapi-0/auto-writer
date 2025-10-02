"""定义数据库 ORM 模型。"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """SQLAlchemy 基类，供所有模型继承。"""


class Article(Base):
    """文章实体模型。"""

    __tablename__ = "articles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)  # 主键自增 id
    title: Mapped[str] = mapped_column(String(255), nullable=False)  # 文章标题
    content: Mapped[str] = mapped_column(Text, nullable=False)  # 文章正文内容
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )  # 创建时间，默认当前 UTC
    keywords: Mapped[list["Keyword"]] = relationship(
        "Keyword", back_populates="article", cascade="all, delete-orphan"
    )  # 关联关键词，删除文章时级联删除关键词
    runs: Mapped[list["RunRecord"]] = relationship(
        "RunRecord", back_populates="article", cascade="all, delete-orphan"
    )  # 关联运行记录


class Keyword(Base):
    """关键词实体模型。"""

    __tablename__ = "keywords"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)  # 主键 id
    article_id: Mapped[int] = mapped_column(ForeignKey("articles.id"), nullable=False)  # 文章外键
    keyword: Mapped[str] = mapped_column(String(128), nullable=False)  # 关键词内容
    article: Mapped[Article] = relationship("Article", back_populates="keywords")  # 反向关联文章


class RunRecord(Base):
    """记录每次生成与投递任务的运行状态。"""

    __tablename__ = "runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)  # 主键 id
    article_id: Mapped[int | None] = mapped_column(
        ForeignKey("articles.id"), nullable=True
    )  # 关联的文章 id，可为空表示失败
    status: Mapped[str] = mapped_column(String(32), nullable=False)  # 运行状态，如 success/failed
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)  # 运行详情或错误信息
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )  # 记录创建时间
    article: Mapped[Article | None] = relationship("Article", back_populates="runs")  # 反向关联文章
