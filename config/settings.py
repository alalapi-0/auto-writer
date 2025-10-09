# -*- coding: utf-8 -*-
"""应用统一配置加载模块，聚合路径、安全与凭据校验逻辑。"""

from __future__ import annotations

import os  # TODO: 读取环境变量，确保兼容现有部署
import re  # TODO: 新增凭据正则校验，阻止格式错误
from dataclasses import dataclass, field  # TODO: 引入 field 以设置目录默认值
from pathlib import Path  # TODO: 处理文件路径，避免字符串硬编码
from typing import List  # TODO: 返回凭据校验错误列表

from dotenv import load_dotenv  # TODO: 继续支持 .env 加载

from app.utils.paths import ensure_subdir, get_app_data_dir  # TODO: 使用统一数据目录入口

BASE_DIR = Path(__file__).resolve().parent.parent  # TODO: 保留仓库根目录定位逻辑
ENV_PATH = BASE_DIR / ".env"  # TODO: 默认环境变量文件路径保持不变

if ENV_PATH.exists():  # TODO: 若存在 .env 文件则加载，兼容原有流程
    load_dotenv(ENV_PATH)  # TODO: 使用 python-dotenv 读取配置，支持本地开发


def _parse_platform_list(raw: str | None, default: List[str]) -> List[str]:  # 新增: 解析平台列表
    """将逗号分隔的环境变量解析为平台列表，移除空白项。"""  # 新增: 函数中文文档

    if not raw:  # 新增: 若环境变量为空则返回默认值
        return list(default)  # 新增: 返回默认列表副本
    items = [item.strip() for item in raw.split(",")]  # 新增: 按逗号拆分并去除空白
    return [item for item in items if item]  # 新增: 过滤空字符串


def _parse_int(raw: str | None, default: int) -> int:  # 新增: 安全解析整数
    """将环境变量解析为整数，失败时回退默认值。"""  # 新增: 函数中文文档

    try:  # 新增: 捕获非法输入
        return int(raw) if raw is not None else default  # 新增: 返回转换结果或默认值
    except ValueError:  # 新增: 捕获转换异常
        return default  # 新增: 回退到默认值


DELIVERY_ENABLED_PLATFORMS = _parse_platform_list(  # 新增: 定义平台开关默认值
    os.getenv("DELIVERY_ENABLED_PLATFORMS"),  # 新增: 读取环境变量覆盖
    ["wechat_mp", "zhihu"],  # 新增: 默认启用公众号与知乎
)  # 新增: 结束平台列表定义
OUTBOX_DIR = os.getenv("OUTBOX_DIR", "./outbox")  # 新增: 定义草稿产出目录
RETRY_BASE_SECONDS = _parse_int(os.getenv("RETRY_BASE_SECONDS"), 300)  # 新增: 定义重试基础秒数
RETRY_MAX_ATTEMPTS = _parse_int(os.getenv("RETRY_MAX_ATTEMPTS"), 5)  # 新增: 定义最大重试次数


class ConfigError(Exception):
    """配置/凭据不合法时抛出该异常，并附带可读信息。"""

    # TODO: 自定义异常便于调用方明确捕获配置问题
    pass


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

    # === 存储相关 ===
    app_dir: Path = field(default_factory=get_app_data_dir)  # TODO: 使用统一应用目录，避免污染仓库
    data_dir: Path = field(default_factory=lambda: ensure_subdir("data"))  # TODO: 数据库存放路径
    logs_dir: Path = field(default_factory=lambda: ensure_subdir("logs"))  # TODO: 日志输出目录
    exports_dir: Path = field(default_factory=lambda: ensure_subdir("exports"))  # TODO: 导出文件目录
    tmp_dir: Path = field(default_factory=lambda: ensure_subdir("tmp"))  # TODO: 临时文件目录
    sqlite_url: str = field(
        default_factory=lambda: f"sqlite:///{(ensure_subdir('data') / 'autowriter.db').as_posix()}"
    )  # TODO: 默认 SQLite 数据库迁移到应用目录

    # === 平台开关与凭据 ===
    enable_wechat_mp: bool = False  # TODO: 微信公众号默认关闭
    wechat_mp_cookie: str | None = None  # TODO: 按需注入 cookie

    enable_zhihu: bool = False  # TODO: 知乎默认关闭
    zhihu_cookie: str | None = None  # TODO: 保存知乎 cookie

    enable_medium: bool = False  # TODO: Medium 默认关闭
    medium_token: str | None = None  # TODO: Medium token

    enable_wordpress: bool = False  # TODO: WordPress 默认关闭
    wp_url: str | None = None  # TODO: WordPress 站点 URL
    wp_user: str | None = None  # TODO: WordPress 用户名
    wp_app_pass: str | None = None  # TODO: WordPress 应用密码

    # === 主题生命周期参数 ===
    lock_expire_minutes: int = 90  # TODO: 软锁超时时长，单位分钟
    delivery_enabled_platforms: List[str] = field(  # 新增: 平台开关列表字段
        default_factory=list  # 新增: 默认使用空列表占位
    )
    outbox_dir: str = "./outbox"  # 新增: 草稿输出目录默认值
    retry_base_seconds: int = 300  # 新增: 重试基础秒数默认值
    retry_max_attempts: int = 5  # 新增: 最大重试次数默认值

    # === 保持原有字段 ===
    database: DatabaseConfig = field(
        default_factory=lambda: DatabaseConfig(
            url=f"sqlite:///{(ensure_subdir('data') / 'autowriter.db').as_posix()}"
        )
    )  # TODO: 兼容旧逻辑，仍提供 DatabaseConfig
    orchestrator: OrchestratorConfig = field(
        default_factory=lambda: OrchestratorConfig(
            daily_article_count=3,
            keyword_recent_cooldown_days=30,
            postrun_enrich_group_size=3,
            enable_postrun_enrich=True,
            timezone="Asia/Tokyo",
        )
    )  # TODO: 默认 orchestrator 参数
    ssh: SSHConfig = field(
        default_factory=lambda: SSHConfig(
            host="",
            user="",
            port=22,
            key_path="",
            workdir=str(ensure_subdir("tmp") / "vps"),
        )
    )  # TODO: 默认 SSH 配置指向 tmp 子目录
    scheduler: SchedulerConfig = field(
        default_factory=lambda: SchedulerConfig(cron_expression="0 9 * * *")
    )  # TODO: 默认调度表达式
    platform_credentials: PlatformCredentials = field(
        default_factory=lambda: PlatformCredentials(
            wordpress_base_url="",
            wordpress_username="",
            wordpress_app_password="",
            medium_integration_token="",
            wechat_app_id="",
            wechat_app_secret="",
        )
    )  # TODO: 保留旧凭据对象供兼容
    openai_api_key: str = ""  # TODO: 兼容历史逻辑保留字段

    @property
    def timezone(self) -> str:
        """向后兼容属性，返回 orchestrator 时区。"""

        return self.orchestrator.timezone

    def validate_credentials(self) -> List[str]:
        """对已启用的平台做“必填/形状”校验，返回错误列表。"""

        # TODO: 校验逻辑返回错误集合而非抛出异常，供 CLI 决策
        errs: List[str] = []

        if self.enable_wechat_mp:
            if not self.wechat_mp_cookie:
                errs.append("WeChatMP: 缺少 wechat_mp_cookie")
            elif "passport.wechat.com" in (self.wechat_mp_cookie or ""):
                errs.append("WeChatMP: cookie 看起来像登录页而非业务 cookie，请重新抓取。")

        if self.enable_zhihu:
            if not self.zhihu_cookie:
                errs.append("Zhihu: 缺少 zhihu_cookie")

        if self.enable_medium:
            if not self.medium_token or len(self.medium_token) < 20:
                errs.append("Medium: 缺少或疑似无效的 medium_token")

        if self.enable_wordpress:
            url_pat = re.compile(r"^https?://")
            if not self.wp_url or not url_pat.match(self.wp_url):
                errs.append("WordPress: wp_url 缺失或格式错误")
            if not self.wp_user:
                errs.append("WordPress: wp_user 缺失")
            if not self.wp_app_pass or len(self.wp_app_pass) < 8:
                errs.append("WordPress: wp_app_pass 缺失或过短")

        for p in [self.data_dir, self.logs_dir, self.exports_dir, self.tmp_dir]:
            try:
                p.mkdir(parents=True, exist_ok=True)
                test = p / ".writable.test"
                test.write_text("ok", encoding="utf-8")
                test.unlink(missing_ok=True)
            except Exception as exc:  # noqa: BLE001
                errs.append(f"目录不可写: {p} -> {exc!r}")

        return errs


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

    # TODO: 统一默认 SQLite 路径到应用数据目录
    default_sqlite_url = f"sqlite:///{(ensure_subdir('data') / 'autowriter.db').as_posix()}"
    db_url = os.getenv("DB_URL") or os.getenv("DATABASE_URL") or default_sqlite_url

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

    tmp_workdir = os.getenv("VPS_WORKDIR") or str(ensure_subdir("tmp") / "vps")
    ssh_config = SSHConfig(
        host=os.getenv("VPS_SSH_HOST", ""),
        user=os.getenv("VPS_SSH_USER", ""),
        port=_get_env_int("VPS_SSH_PORT", 22),
        key_path=os.getenv("VPS_SSH_KEY_PATH", ""),
        workdir=tmp_workdir,
    )

    platform_credentials = PlatformCredentials(
        wordpress_base_url=os.getenv("WORDPRESS_BASE_URL", ""),
        wordpress_username=os.getenv("WORDPRESS_USERNAME", ""),
        wordpress_app_password=os.getenv("WORDPRESS_APP_PASSWORD", ""),
        medium_integration_token=os.getenv("MEDIUM_INTEGRATION_TOKEN", ""),
        wechat_app_id=os.getenv("WECHAT_APP_ID", ""),
        wechat_app_secret=os.getenv("WECHAT_APP_SECRET", ""),
    )

    settings_obj = Settings(
        sqlite_url=default_sqlite_url,
        database=DatabaseConfig(url=db_url),
        orchestrator=orchestrator_config,
        ssh=ssh_config,
        scheduler=scheduler_config,
        platform_credentials=platform_credentials,
        openai_api_key=os.getenv("OPENAI_API_KEY", ""),
        enable_wechat_mp=_get_env_bool("ENABLE_WECHAT_MP", False),
        wechat_mp_cookie=os.getenv("WECHAT_MP_COOKIE"),
        enable_zhihu=_get_env_bool("ENABLE_ZHIHU", False),
        zhihu_cookie=os.getenv("ZHIHU_COOKIE"),
        enable_medium=_get_env_bool("ENABLE_MEDIUM", False),
        medium_token=os.getenv("MEDIUM_TOKEN"),
        enable_wordpress=_get_env_bool("ENABLE_WORDPRESS", False),
        wp_url=os.getenv("WP_URL"),
        wp_user=os.getenv("WP_USER"),
        wp_app_pass=os.getenv("WP_APP_PASS"),
        delivery_enabled_platforms=list(DELIVERY_ENABLED_PLATFORMS),  # 新增: 注入平台开关配置
        outbox_dir=OUTBOX_DIR,  # 新增: 注入 outbox 目录
        retry_base_seconds=RETRY_BASE_SECONDS,  # 新增: 注入重试基础秒数
        retry_max_attempts=RETRY_MAX_ATTEMPTS,  # 新增: 注入最大重试次数
    )

    return settings_obj


settings = get_settings()  # 模块级别创建配置实例，供其他模块直接引用
