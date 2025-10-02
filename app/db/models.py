"""定义数据库 ORM 模型。

模型涵盖文章、关键词以及运行记录表，每个字段都附带中文注释说明用途。
"""

from __future__ import annotations

from datetime import datetime  # 定义时间戳字段默认值

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text  # 导入 ORM 字段类型
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship  # ORM 基类与类型标注


class Base(DeclarativeBase):
    """SQLAlchemy 基类，供所有模型继承。"""


class Article(Base):
    """文章实体模型，记录生成的正文与关键词关联。"""

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
    """关键词实体模型。

    将文章与多个关键词建立多对一关系，为去重算法提供历史词库。
    """

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


class PsychologyTheme(Base):
    """存储心理学关键词与影视角色组合，供文章生成调用。"""

    __tablename__ = "psychology_themes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)  # 主键 id
    psychology_keyword: Mapped[str] = mapped_column(String(128), nullable=False)  # 心理学关键词
    psychology_definition: Mapped[str] = mapped_column(String(255), nullable=False)  # 概念定义
    character_name: Mapped[str] = mapped_column(String(128), nullable=False)  # 影视角色名称
    show_name: Mapped[str] = mapped_column(String(128), nullable=False)  # 影视剧名称
    used: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)  # 是否已被使用
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )  # 创建时间
