# -*- coding: utf-8 -*-
"""应用统一配置加载模块，聚合路径、安全与凭据校验逻辑。"""

from __future__ import annotations

import os  # 使用标准库 os 读取环境变量，兼容部署时的配置注入
import re  # 使用正则表达式校验部分凭据形状，避免格式错误
from dataclasses import dataclass, field  # 从 dataclasses 导入 dataclass 与 field 以构建配置数据类
from pathlib import Path  # 使用 Path 统一处理文件路径，避免硬编码字符串
from typing import List  # 引入 List 类型注解以提升可读性

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


def _get_env_int(name: str, default: int) -> int:  # 新增: 封装整型环境变量读取
    """读取整数环境变量，失败时回退默认值。"""  # 中文注释说明用途

    try:  # 捕获转换异常
        return int(os.getenv(name, default))  # 若读取失败则返回默认值
    except ValueError:  # 非法数值
        return default  # 使用默认值兜底


def _get_env_bool(name: str, default: bool) -> bool:  # 新增: 读取布尔环境变量
    """解析布尔环境变量，识别常见真值文本。"""  # 中文注释说明

    raw = os.getenv(name)  # 读取原始字符串
    if raw is None:  # 未设置
        return default  # 返回默认值
    return raw.lower() in {"1", "true", "yes", "on"}  # 判断常见真值


DELIVERY_ENABLED_PLATFORMS = _parse_platform_list(  # 从环境变量解析启用的平台列表
    os.getenv("DELIVERY_ENABLED_PLATFORMS"),  # 读取 DELIVERY_ENABLED_PLATFORMS 环境变量用于覆盖默认值
    ["wechat_mp", "zhihu"],  # 默认启用微信公众号与知乎平台
)  # 结束平台列表常量定义
OUTBOX_DIR = os.getenv("OUTBOX_DIR", "./outbox")  # 读取 OUTBOX_DIR 环境变量，默认输出到 ./outbox
LOG_DIR = os.getenv("LOG_DIR", "./logs")  # 读取 LOG_DIR 环境变量，默认日志目录为 ./logs
EXPORT_DIR = os.getenv("EXPORT_DIR", "./exports")  # 读取 EXPORT_DIR 环境变量，默认导出目录为 ./exports
RETRY_BASE_SECONDS = _parse_int(os.getenv("RETRY_BASE_SECONDS"), 300)  # 读取 RETRY_BASE_SECONDS 环境变量，默认 300 秒
RETRY_MAX_ATTEMPTS = _parse_int(os.getenv("RETRY_MAX_ATTEMPTS"), 5)  # 读取 RETRY_MAX_ATTEMPTS 环境变量，默认重试 5 次
THEME_LOW_WATERMARK = _parse_int(os.getenv("THEME_LOW_WATERMARK"), 20)  # 读取 THEME_LOW_WATERMARK 环境变量，默认低水位 20
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()  # 读取 LOG_LEVEL 环境变量控制日志级别，默认 INFO
PLAYWRIGHT_HEADLESS = _get_env_bool("HEADLESS", True)  # 新增: 控制浏览器是否无头
SESSION_DIR_DEFAULT = os.getenv("SESSION_DIR", "./.sessions")  # 新增: 会话 Cookie 存放目录默认值
WECHAT_COOKIE_PATH_DEFAULT = os.getenv(
    "WECHAT_COOKIE_PATH", "./.sessions/wechat_mp.cookies.json"
)  # 新增: 公众号 Cookie 文件路径
ZHIHU_COOKIE_PATH_DEFAULT = os.getenv(
    "ZHIHU_COOKIE_PATH", "./.sessions/zhihu.cookies.json"
)  # 新增: 知乎 Cookie 文件路径
PLAYWRIGHT_TIMEOUT_MS_DEFAULT = _get_env_int("PW_TIMEOUT_MS", 30000)  # 新增: 浏览器操作超时时间
PLAYWRIGHT_SLOWMO_MS_DEFAULT = _get_env_int("PW_SLOWMO_MS", 0)  # 新增: 慢动作延迟，便于调试
PLAYWRIGHT_SCREENSHOT_DIR_DEFAULT = os.getenv(
    "PW_SHOT_DIR", "./logs/screenshots"
)  # 新增: 截图输出目录
PLAYWRIGHT_TRACING_DEFAULT = _get_env_bool("PW_TRACING", False)  # 新增: 是否开启 tracing 记录


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
    theme_low_watermark: int = 20  # 新增: 主题库存低水位默认值
    playwright_headless: bool = True  # 新增: Playwright 是否无头运行
    session_dir: str = "./.sessions"  # 新增: 会话 Cookie 目录
    wechat_cookie_path: str = "./.sessions/wechat_mp.cookies.json"  # 新增: 公众号 Cookie 文件路径
    zhihu_cookie_path: str = "./.sessions/zhihu.cookies.json"  # 新增: 知乎 Cookie 文件路径
    playwright_timeout_ms: int = 30000  # 新增: 浏览器默认超时
    playwright_slowmo_ms: int = 0  # 新增: 调试慢动作毫秒
    playwright_screenshot_dir: str = "./logs/screenshots"  # 新增: 截图输出目录
    playwright_tracing: bool = False  # 新增: 是否开启 tracing

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
        logs_dir=Path(LOG_DIR),  # 新增: 使用环境变量指定日志目录
        exports_dir=Path(EXPORT_DIR),  # 新增: 使用环境变量指定导出目录
        theme_low_watermark=THEME_LOW_WATERMARK,  # 新增: 使用环境变量覆盖主题低水位
        playwright_headless=PLAYWRIGHT_HEADLESS,  # 新增: Playwright 无头配置
        session_dir=SESSION_DIR_DEFAULT,  # 新增: 会话目录设置
        wechat_cookie_path=WECHAT_COOKIE_PATH_DEFAULT,  # 新增: 公众号 Cookie 路径
        zhihu_cookie_path=ZHIHU_COOKIE_PATH_DEFAULT,  # 新增: 知乎 Cookie 路径
        playwright_timeout_ms=PLAYWRIGHT_TIMEOUT_MS_DEFAULT,  # 新增: 操作超时
        playwright_slowmo_ms=PLAYWRIGHT_SLOWMO_MS_DEFAULT,  # 新增: 慢动作间隔
        playwright_screenshot_dir=PLAYWRIGHT_SCREENSHOT_DIR_DEFAULT,  # 新增: 截图目录
        playwright_tracing=PLAYWRIGHT_TRACING_DEFAULT,  # 新增: tracing 开关
    )

    return settings_obj


settings = get_settings()  # 模块级别创建配置实例，供其他模块直接引用


def _mask_value(value: str | None) -> str:  # 定义内部函数用于屏蔽敏感配置
    """对敏感信息进行脱敏，保留首尾字符。"""  # 中文文档说明函数用途

    if not value:  # 当值为空时直接返回空字符串
        return ""  # 返回空串避免打印 None
    if len(value) <= 4:  # 若字符串过短则直接返回掩码
        return "*" * len(value)  # 以相同长度的星号替代
    return f"{value[0]}{'*' * (len(value) - 2)}{value[-1]}"  # 保留首尾字符并遮蔽中间部分


def print_config(mask_secrets: bool = True) -> None:  # 定义打印配置的便捷函数
    """输出关键配置，支持屏蔽敏感字段。"""  # 函数中文说明

    config_items = [  # 构造待打印配置项列表
        ("数据库 URL", settings.database.url, True),  # 数据库连接字符串属于敏感信息
        ("SQLite URL", settings.sqlite_url, False),  # SQLite 本地路径相对不敏感
        ("OUTBOX_DIR", settings.outbox_dir, False),  # 草稿输出目录
        ("LOG_DIR", str(settings.logs_dir), False),  # 日志目录
        ("EXPORT_DIR", str(settings.exports_dir), False),  # 导出目录
        ("重试基础秒数", str(settings.retry_base_seconds), False),  # 重试初始间隔
        ("最大重试次数", str(settings.retry_max_attempts), False),  # 重试上限
        ("主题低水位", str(settings.theme_low_watermark), False),  # 主题库存低水位
        ("启用平台", ",".join(settings.delivery_enabled_platforms), False),  # 平台启用列表
        ("PLAYWRIGHT_HEADLESS", str(settings.playwright_headless), False),  # 浏览器无头模式
        ("SESSION_DIR", settings.session_dir, False),  # 会话目录
        ("WECHAT_COOKIE_PATH", settings.wechat_cookie_path, False),  # 公众号 Cookie 路径
        ("ZHIHU_COOKIE_PATH", settings.zhihu_cookie_path, False),  # 知乎 Cookie 路径
        ("PW_TIMEOUT_MS", str(settings.playwright_timeout_ms), False),  # 浏览器超时
        ("PW_SLOWMO_MS", str(settings.playwright_slowmo_ms), False),  # 慢动作毫秒
        ("PW_SHOT_DIR", settings.playwright_screenshot_dir, False),  # 截图目录
        ("PW_TRACING", str(settings.playwright_tracing), False),  # tracing 开关
        ("OpenAI Key", settings.openai_api_key, True),  # OpenAI 凭据需脱敏
        ("WeChat Cookie", settings.wechat_mp_cookie or "", True),  # 微信凭据
        ("Zhihu Cookie", settings.zhihu_cookie or "", True),  # 知乎凭据
        ("Medium Token", settings.medium_token or "", True),  # Medium 凭据
        ("WordPress URL", settings.wp_url or "", False),  # WordPress 站点信息
        ("日志级别", LOG_LEVEL, False),  # 当前日志级别
    ]  # 列表定义结束

    print("当前配置概览:")  # 打印标题
    for label, value, sensitive in config_items:  # 遍历配置项
        display_value = _mask_value(value) if mask_secrets and sensitive else value  # 根据敏感标记决定是否脱敏
        print(f" - {label}: {display_value}")  # 逐行输出键值对
