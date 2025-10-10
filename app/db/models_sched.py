"""调度/账号相关 ORM 模型定义，独立于主业务库。"""  # 模块中文说明

from __future__ import annotations  # 启用未来注解语法

from datetime import datetime, date  # 处理时间字段与日期列
from sqlalchemy import (  # 引入 SQLAlchemy 类型与约束工具
    Boolean,  # 布尔值列
    Date,  # 日期列用于记录运行日期
    DateTime,  # 日期时间列
    ForeignKey,  # 外键约束
    Index,  # 普通索引构造器
    Integer,  # 整型列
    String,  # 可变字符串列
    Text,  # 文本列
    UniqueConstraint,  # 唯一约束
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship  # 导入 ORM 基类与映射工具


class SchedBase(DeclarativeBase):  # 定义调度数据库的基类
    """调度数据库独立基类，避免与主库混用。"""  # 类中文说明


class TimestampMixin:  # 通用时间戳混入
    """统一的创建/更新时间混入类，供多表复用。"""  # 类中文说明

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)  # 创建时间列
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )  # 更新时间列


class User(SchedBase, TimestampMixin):  # 用户表定义
    """Dashboard 登录用户表，包含角色与状态。"""  # 类中文说明

    __tablename__ = "users"  # 表名

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)  # 主键自增 ID
    username: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)  # 用户名唯一且必填
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)  # 密码哈希存储
    role: Mapped[str] = mapped_column(String(16), nullable=False)  # 角色字段：admin/operator/viewer
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)  # 账号是否启用

    tokens: Mapped[list["AuthToken"]] = relationship(back_populates="user", cascade="all, delete-orphan")  # 关联 token


class AuthToken(SchedBase, TimestampMixin):  # 令牌黑名单表
    """记录已签发的 JWT jti 以便失效管理。"""  # 类中文说明

    __tablename__ = "auth_tokens"  # 表名

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)  # 主键自增 ID
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)  # 关联用户 ID
    jti: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)  # JWT 唯一标识
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)  # 过期时间

    user: Mapped[User] = relationship(back_populates="tokens")  # 反向引用用户


class Profile(SchedBase, TimestampMixin):  # Profile 档案表
    """记录每个 Profile 的元数据与 YAML 路径。"""  # 类中文说明

    __tablename__ = "profiles"  # 表名

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)  # 主键 ID
    name: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)  # Profile 名称
    yaml_path: Mapped[str] = mapped_column(String(255), nullable=False)  # YAML 文件路径
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)  # 是否启用
    dispatch_mode: Mapped[str] = mapped_column(String(16), default="queue", nullable=False)  # 调度执行模式


class Schedule(SchedBase, TimestampMixin):  # 调度计划表
    """为 Profile 配置 cron 调度表达式。"""  # 类中文说明

    __tablename__ = "schedules"  # 表名

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)  # 主键 ID
    profile_id: Mapped[int] = mapped_column(ForeignKey("profiles.id"), nullable=False)  # 关联 Profile
    cron_expr: Mapped[str] = mapped_column(String(64), nullable=False)  # Cron 表达式
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)  # 下次运行时间
    tz: Mapped[str] = mapped_column(String(32), nullable=False, default="Asia/Tokyo")  # 时区设置
    is_paused: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)  # 是否暂停
    jitter_sec: Mapped[int] = mapped_column(Integer, default=0, nullable=False)  # 抖动秒数
    coalesce: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)  # 是否合并错过的任务
    misfire_grace_sec: Mapped[int] = mapped_column(Integer, default=300, nullable=False)  # 超时宽限秒数

    profile: Mapped[Profile] = relationship()  # 关联 Profile 记录


class JobRun(SchedBase):  # 运行记录表
    """调度任务执行结果记录。"""  # 类中文说明

    __tablename__ = "job_runs"  # 表名

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)  # 主键 ID
    profile_id: Mapped[int] = mapped_column(ForeignKey("profiles.id"), nullable=False)  # 关联 Profile
    idempotency_key: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)  # 新增: 幂等键
    run_date: Mapped[date] = mapped_column(Date, nullable=False)  # 新增: 运行日期
    batch_no: Mapped[str] = mapped_column(String(32), default="default", nullable=False)  # 新增: 批次编号
    started_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)  # 开始时间
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)  # 结束时间
    status: Mapped[str] = mapped_column(String(16), default="running", nullable=False)  # 状态
    error: Mapped[str | None] = mapped_column(Text, nullable=True)  # 错误信息
    emitted_articles: Mapped[int] = mapped_column(Integer, default=0, nullable=False)  # 生成文章数量
    delivered_success: Mapped[int] = mapped_column(Integer, default=0, nullable=False)  # 投递成功数量
    delivered_failed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)  # 投递失败数量

    profile: Mapped[Profile] = relationship()  # 关联 Profile 记录


class TaskQueue(SchedBase):  # 队列表定义
    """用于分布式 Worker 拉取执行的任务队列。"""  # 类中文说明

    __tablename__ = "task_queue"  # 指定表名

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)  # 主键自增 ID
    profile_id: Mapped[int] = mapped_column(ForeignKey("profiles.id"), nullable=False)  # 关联 Profile
    payload_json: Mapped[str] = mapped_column(Text, nullable=False)  # 序列化的任务负载
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)  # 入队时间
    available_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)  # 可被租约的时间
    priority: Mapped[int] = mapped_column(Integer, default=0, nullable=False)  # 优先级数值，数字越大越优先
    status: Mapped[str] = mapped_column(String(16), default="pending", nullable=False)  # 任务状态
    lease_until: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)  # 租约到期时间
    lease_by: Mapped[str | None] = mapped_column(String(128), nullable=True)  # 当前租约持有的 Worker 名称
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)  # 已尝试次数
    max_attempts: Mapped[int] = mapped_column(Integer, default=3, nullable=False)  # 最大尝试次数
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)  # 最近一次错误信息
    idempotency_key: Mapped[str | None] = mapped_column(String(128), nullable=True)  # 幂等键避免重复入队

    __table_args__ = (  # 附加表级约束
        UniqueConstraint("idempotency_key", name="uq_taskqueue_idempo"),  # 幂等键唯一约束
    )


class Heartbeat(SchedBase):  # Worker 心跳表
    """保存 Worker 最近在线时间与附加信息。"""  # 类中文说明

    __tablename__ = "worker_heartbeat"  # 指定表名

    agent_name: Mapped[str] = mapped_column(String(128), primary_key=True)  # Worker 名称主键
    last_seen_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)  # 最近心跳时间
    meta_json: Mapped[str | None] = mapped_column(Text, nullable=True)  # 额外元数据 JSON


class MetricEvent(SchedBase):  # 指标事件表
    """采集生成、投递等过程中的指标事件。"""  # 类中文说明

    __tablename__ = "metric_events"  # 表名

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)  # 主键 ID
    ts: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)  # 时间戳
    kind: Mapped[str] = mapped_column(String(32), nullable=False)  # 指标类型
    profile_id: Mapped[int | None] = mapped_column(Integer, nullable=True)  # Profile ID，可空
    platform: Mapped[str | None] = mapped_column(String(32), nullable=True)  # 平台名
    key: Mapped[str] = mapped_column(String(64), nullable=False)  # 指标键
    value: Mapped[float] = mapped_column(Integer, default=0, nullable=False)  # 指标值，使用整数存储


class PluginRegistry(SchedBase, TimestampMixin):  # 插件注册表
    """记录已安装插件的元数据与状态。"""  # 类中文说明

    __tablename__ = "plugin_registry"  # 表名

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)  # 主键 ID
    name: Mapped[str] = mapped_column(String(128), nullable=False)  # 插件名称
    kind: Mapped[str] = mapped_column(String(32), nullable=False)  # 插件类型 filters/exporters
    path: Mapped[str] = mapped_column(String(255), nullable=False)  # 插件物理路径
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)  # 是否启用
    version: Mapped[str] = mapped_column(String(32), nullable=False)  # 插件版本
    installed_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)  # 安装时间
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)  # 最近加载错误信息


Index("idx_schedule_profile", Schedule.profile_id)  # 为调度表添加 Profile 维度索引
Index("idx_jobrun_started", JobRun.started_at)  # JobRun 开始时间索引
Index("idx_jobrun_profile", JobRun.profile_id)  # JobRun Profile 索引
Index("idx_jobrun_date", JobRun.run_date)  # 新增: JobRun 运行日期索引
Index(
    "idx_taskqueue_status_available",
    TaskQueue.status,
    TaskQueue.available_at,
)  # 队列状态+可用时间索引
Index("idx_taskqueue_priority", TaskQueue.priority)  # 队列优先级索引
Index("idx_taskqueue_lease", TaskQueue.lease_by)  # 队列租约持有者索引
Index("idx_heartbeat_seen", Heartbeat.last_seen_at)  # 心跳最近时间索引
Index("idx_metric_ts", MetricEvent.ts)  # 指标时间索引
Index("idx_metric_key", MetricEvent.key)  # 指标键索引
