"""定义数据库 ORM 模型。

模型覆盖角色、关键词、运行记录等核心表结构，全部字段均附带中文注释说明用途。
"""

from __future__ import annotations

from datetime import datetime, date  # 处理时间字段

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    JSON,  # 新增: 引入 JSON 类型存储 payload
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """SQLAlchemy 基类，供所有模型继承。"""


class TimestampMixin:
    """统一的创建/更新时间字段。"""

    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )  # 创建时间，默认当前 UTC
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )  # 更新时间，每次写入自动刷新


class Character(Base):
    """主角色库，收录心理学分析常用角色。"""

    __tablename__ = "characters"
    __table_args__ = (UniqueConstraint("name", "work", name="uq_character_name_work"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)  # 主键 id
    name: Mapped[str] = mapped_column(String(128), nullable=False)  # 角色名称
    work: Mapped[str] = mapped_column(String(128), nullable=False)  # 作品名称
    traits: Mapped[str] = mapped_column(Text, nullable=False)  # 角色心理/性格特质，JSON 或逗号分隔字符串
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )  # 创建时间


class ExtendedCharacter(Base):
    """扩展角色库，用于补充临时引入的角色。"""

    __tablename__ = "extended_characters"
    __table_args__ = (
        UniqueConstraint("name", "work", name="uq_extended_character_name_work"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)  # 主键 id
    name: Mapped[str] = mapped_column(String(128), nullable=False)  # 角色名称
    work: Mapped[str] = mapped_column(String(128), nullable=False)  # 作品名称
    traits: Mapped[str] = mapped_column(Text, nullable=False)  # 心理特质描述
    source: Mapped[str] = mapped_column(String(128), nullable=True)  # 数据来源说明，可为空
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )  # 创建时间


class Keyword(Base):
    """关键词表，记录心理学主题词及其使用情况。"""

    __tablename__ = "keywords"
    __table_args__ = (UniqueConstraint("keyword", name="uq_keyword_value"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)  # 主键 id
    keyword: Mapped[str] = mapped_column(String(128), nullable=False)  # 关键词文本
    category: Mapped[str | None] = mapped_column(String(64), nullable=True)  # 可选分类
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)  # 最近使用时间
    usage_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)  # 使用次数累计
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)  # 是否仍可用
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )  # 创建时间


class Run(Base):
    """一次 orchestrator 执行的聚合记录。"""

    __tablename__ = "runs"
    __table_args__ = (UniqueConstraint("run_id", name="uq_run_run_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)  # 主键 id
    run_id: Mapped[str] = mapped_column(String(64), nullable=False)  # 运行唯一标识
    run_date: Mapped[date] = mapped_column(Date, nullable=False)  # 运行对应日期
    planned_articles: Mapped[int] = mapped_column(Integer, nullable=False)  # 计划文章数
    keywords_consumed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)  # 已消耗关键词数量
    keywords_added: Mapped[int] = mapped_column(Integer, default=0, nullable=False)  # 事后补充数量
    status: Mapped[str] = mapped_column(String(32), default="pending", nullable=False)  # 状态字段
    metadata_path: Mapped[str | None] = mapped_column(String(255), nullable=True)  # 记录 job.json 路径
    result_path: Mapped[str | None] = mapped_column(String(255), nullable=True)  # 记录 result.json 路径
    error: Mapped[str | None] = mapped_column(Text, nullable=True)  # 新增: 运行错误信息
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )  # 创建时间
    updated_at: Mapped[datetime] = mapped_column(  # 新增: 更新时间字段
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    articles: Mapped[list["ArticleDraft"]] = relationship(
        back_populates="run", cascade="all, delete-orphan"
    )  # 反向关联文章草稿


class ArticleDraft(Base):
    """记录某次运行生成的文章草稿元数据。"""

    __tablename__ = "articles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)  # 主键 id
    run_id: Mapped[int | None] = mapped_column(ForeignKey("runs.id"), nullable=True)  # 关联运行表
    character_name: Mapped[str] = mapped_column(String(128), nullable=False)  # 角色名称
    work: Mapped[str] = mapped_column(String(128), nullable=False)  # 作品名称
    keyword: Mapped[str] = mapped_column(String(128), nullable=False)  # 对应关键词
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)  # 草稿标题，可为空
    status: Mapped[str] = mapped_column(String(32), default="draft", nullable=False)  # 草稿状态
    content: Mapped[str | None] = mapped_column(Text, nullable=True)  # 生成的正文内容
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )  # 创建时间

    run: Mapped[Run | None] = relationship("Run", back_populates="articles")  # 反向引用
    platform_logs: Mapped[list["PlatformLog"]] = relationship(
        back_populates="article", cascade="all, delete-orphan"
    )  # 关联平台投递记录
    quality_audit: Mapped["ContentAudit" | None] = relationship(
        back_populates="article", cascade="all, delete-orphan", uselist=False
    )  # 新增: 关联质量闸门记录，一篇文章对应一条审计


class PlatformLog(Base):
    """记录投递到各平台的结果日志。"""

    __tablename__ = "platform_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)  # 主键 id
    article_id: Mapped[int] = mapped_column(
        ForeignKey("articles.id"), nullable=False
    )  # 关联文章草稿
    platform: Mapped[str] = mapped_column(String(64), nullable=False)  # 平台名称
    target_id: Mapped[str | None] = mapped_column(String(255), nullable=True)  # 新增: 平台返回的草稿 ID
    status: Mapped[str] = mapped_column(String(32), default="pending", nullable=False)  # 新增: 投递状态
    ok: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)  # 是否成功
    id_or_url: Mapped[str | None] = mapped_column(String(255), nullable=True)  # 返回的草稿 id 或链接
    error: Mapped[str | None] = mapped_column(Text, nullable=True)  # 错误信息
    attempt_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)  # 新增: 尝试次数
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)  # 新增: 最近一次错误描述
    next_retry_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)  # 新增: 下次重试时间
    prompt_variant: Mapped[str | None] = mapped_column(String(64), nullable=True)  # 新增: 记录投递时使用的 Prompt 版本
    payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # 新增: 存档投递材料
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )  # 记录时间

    article: Mapped[ArticleDraft] = relationship("ArticleDraft", back_populates="platform_logs")  # 反向引用


class ContentAudit(Base):
    """存储质量闸门的打分结果与复核状态。"""

    __tablename__ = "content_audits"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)  # 主键 id
    article_id: Mapped[int] = mapped_column(ForeignKey("articles.id"), nullable=False)  # 关联文章草稿
    prompt_variant: Mapped[str | None] = mapped_column(String(64), nullable=True)  # 使用的 Prompt Variant
    scores: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)  # 指标得分 JSON
    reasons: Mapped[list] = mapped_column(JSON, nullable=False, default=list)  # 未通过原因列表
    attempts: Mapped[list] = mapped_column(JSON, nullable=False, default=list)  # 尝试记录，包含每轮 Variant
    passed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)  # 是否通过质量闸门
    fallback_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)  # 触发回退次数
    manual_review: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)  # 是否进入人工复核
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )  # 创建时间

    article: Mapped[ArticleDraft] = relationship("ArticleDraft", back_populates="quality_audit")  # 反向引用文章


class UsedPair(Base):
    """记录 (角色, 作品, 关键词) 的使用历史，用于去重。"""

    __tablename__ = "used_pairs"
    __table_args__ = (
        UniqueConstraint(
            "character_name",
            "work",
            "keyword",
            "used_on",
            name="uq_used_pair_unique_day",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)  # 主键 id
    character_name: Mapped[str] = mapped_column(String(128), nullable=False)  # 角色名称
    work: Mapped[str] = mapped_column(String(128), nullable=False)  # 作品名称
    keyword: Mapped[str] = mapped_column(String(128), nullable=False)  # 使用的关键词
    run_id: Mapped[str] = mapped_column(String(64), nullable=False)  # 对应运行 ID
    used_on: Mapped[date] = mapped_column(Date, nullable=False)  # 使用日期
    similarity_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)  # 相似度哈希占位
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )  # 创建时间
