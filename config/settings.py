"""应用统一配置加载模块。

该模块负责：
* 解析 .env 文件与系统环境变量；
* 聚合数据库、调度策略、SSH 等配置；
* 暴露 ``settings`` 对象供 orchestrator 与 worker 调用。
"""

from __future__ import annotations

import os  # 读取环境变量
from dataclasses import dataclass  # 构造配置数据类
from pathlib import Path  # 处理文件路径
from dotenv import load_dotenv  # 用于加载 .env 文件内容

BASE_DIR = Path(__file__).resolve().parent.parent  # 计算项目根目录，便于定位资源文件
ENV_PATH = BASE_DIR / ".env"  # 默认环境变量文件路径

if ENV_PATH.exists():  # 若存在 .env 文件则加载
    load_dotenv(ENV_PATH)  # 使用 python-dotenv 读取配置，支持本地开发


@dataclass(slots=True)
class DatabaseConfig:
    """数据库配置数据类，封装单一连接 URL。"""

    url: str  # SQLAlchemy 可识别的数据库连接字符串

    @property
    def default_url(self) -> str:
        """兼容旧版本调用，返回同一个 URL。"""

        return self.url


@dataclass(slots=True)
class OrchestratorConfig:
    """本机 orchestrator 调度策略配置。"""

    daily_article_count: int  # 每日目标文章数量
    keyword_recent_cooldown_days: int  # 关键词冷却窗口（天）
    postrun_enrich_group_size: int  # 事后补充的分组阈值
    enable_postrun_enrich: bool  # 是否开启补充策略
    timezone: str  # 统一时区设置


@dataclass(slots=True)
class SSHConfig:
    """VPS SSH 连接配置。"""

    host: str  # SSH 主机名或 IP
    user: str  # 登录用户名
    port: int  # SSH 端口
    key_path: str  # 私钥路径
    workdir: str  # VPS 临时工作目录


@dataclass(slots=True)
class SchedulerConfig:
    """调度 cron 配置。"""

    cron_expression: str  # cron 表达式，默认每日一次


@dataclass(slots=True)
class PlatformCredentials:
    """平台草稿投递所需凭据，运行时注入 VPS。"""

    wordpress_base_url: str  # WordPress 站点 URL
    wordpress_username: str  # WordPress 用户名
    wordpress_app_password: str  # WordPress 应用密码
    medium_integration_token: str  # Medium token
    wechat_app_id: str  # 微信公众号 AppID
    wechat_app_secret: str  # 微信公众号 AppSecret


@dataclass(slots=True)
class Settings:
    """封装应用所有配置的主数据类。"""

    database: DatabaseConfig  # 数据库连接信息
    orchestrator: OrchestratorConfig  # 调度与策略
    ssh: SSHConfig  # SSH 链接配置
    scheduler: SchedulerConfig  # cron 配置
    platform_credentials: PlatformCredentials  # 平台凭据
    openai_api_key: str = ""  # 兼容历史逻辑保留字段

    @property
    def timezone(self) -> str:
        """向后兼容属性，返回 orchestrator 时区。"""

        return self.orchestrator.timezone


def _get_env_int(name: str, default: int) -> int:
    """读取整数环境变量，失败时回退默认值。"""

    try:
        return int(os.getenv(name, default))
    except ValueError:
        return default


def _get_env_bool(name: str, default: bool) -> bool:
    """解析布尔环境变量，识别常见真值文本。"""

    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.lower() in {"1", "true", "yes", "on"}


def get_settings() -> Settings:
    """读取环境变量并生成配置对象。"""

    # 数据库：优先使用 DB_URL，兼容历史 DATABASE_URL
    db_url = os.getenv("DB_URL") or os.getenv("DATABASE_URL", "sqlite:///./autowriter_local.db")

    orchestrator_config = OrchestratorConfig(
        daily_article_count=_get_env_int("DAILY_ARTICLE_COUNT", 3),
        keyword_recent_cooldown_days=_get_env_int("KEYWORD_RECENT_COOLDOWN_DAYS", 30),
        postrun_enrich_group_size=_get_env_int("POSTRUN_ENRICH_GROUP_SIZE", 3),
        enable_postrun_enrich=_get_env_bool("ENABLE_POSTRUN_ENRICH", True),
        timezone=os.getenv("TIMEZONE", "Asia/Tokyo"),
    )

    scheduler_config = SchedulerConfig(
        cron_expression=os.getenv("SCHEDULE_CRON", "0 9 * * *"),
    )

    ssh_config = SSHConfig(
        host=os.getenv("VPS_SSH_HOST", ""),
        user=os.getenv("VPS_SSH_USER", ""),
        port=_get_env_int("VPS_SSH_PORT", 22),
        key_path=os.getenv("VPS_SSH_KEY_PATH", ""),
        workdir=os.getenv("VPS_WORKDIR", "/tmp/autowriter_run"),
    )

    platform_credentials = PlatformCredentials(
        wordpress_base_url=os.getenv("WORDPRESS_BASE_URL", ""),
        wordpress_username=os.getenv("WORDPRESS_USERNAME", ""),
        wordpress_app_password=os.getenv("WORDPRESS_APP_PASSWORD", ""),
        medium_integration_token=os.getenv("MEDIUM_INTEGRATION_TOKEN", ""),
        wechat_app_id=os.getenv("WECHAT_APP_ID", ""),
        wechat_app_secret=os.getenv("WECHAT_APP_SECRET", ""),
    )

    return Settings(
        database=DatabaseConfig(url=db_url),
        orchestrator=orchestrator_config,
        ssh=ssh_config,
        scheduler=scheduler_config,
        platform_credentials=platform_credentials,
        openai_api_key=os.getenv("OPENAI_API_KEY", ""),
    )


settings = get_settings()  # 模块级别创建配置实例，供其他模块直接引用
