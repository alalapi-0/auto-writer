"""应用统一配置加载模块。

该模块负责：
* 解析 .env 文件与系统环境变量；
* 组织数据库、调度器、时区等配置项；
* 提供全局可直接引用的 ``settings`` 对象。
"""

from __future__ import annotations

import os  # 读取环境变量
from dataclasses import dataclass  # 构建不可变配置对象
from pathlib import Path  # 处理文件路径
from typing import Optional  # 声明可选类型

from dotenv import load_dotenv  # 用于加载 .env 文件内容

BASE_DIR = Path(__file__).resolve().parent.parent  # 计算项目根目录，便于定位资源文件
ENV_PATH = BASE_DIR / ".env"  # 默认的环境变量文件路径

if ENV_PATH.exists():  # 若存在 .env 文件则加载其中的变量
    load_dotenv(ENV_PATH)  # 使用 python-dotenv 读取配置，支持本地开发


@dataclass(slots=True)
class DatabaseConfig:
    """数据库配置数据类，封装多种数据库连接信息。"""

    default_url: str  # 本地或开发环境使用的默认数据库连接字符串
    postgres_url: Optional[str]  # 生产环境 PostgreSQL 连接字符串，可为空


@dataclass(slots=True)
class SchedulerConfig:
    """调度相关配置数据类。"""

    cron_expression: str  # 调度表达式字符串，遵循 cron 格式


@dataclass(slots=True)
class Settings:
    """封装应用所有配置的主数据类。"""

    openai_api_key: str  # 调用大模型的 API Key
    database: DatabaseConfig  # 数据库配置子对象
    scheduler: SchedulerConfig  # 调度配置子对象
    timezone: str  # 调度与日志使用的时区信息


def get_settings() -> Settings:
    """读取环境变量并生成配置对象。"""

    openai_api_key = os.getenv("OPENAI_API_KEY", "")  # 读取 OPENAI_API_KEY，默认空字符串
    database_url = os.getenv("DATABASE_URL", "sqlite:///./autowriter.db")  # 读取数据库连接
    postgres_url = os.getenv("POSTGRES_URL")  # 生产环境连接字符串允许为空
    cron_expression = os.getenv("SCHEDULE_CRON", "0 9 * * *")  # 默认每日 9 点执行
    timezone = os.getenv("TIMEZONE", "Asia/Shanghai")  # 默认使用东八区时区

    database_config = DatabaseConfig(  # 构造数据库配置数据类实例
        default_url=database_url,
        postgres_url=postgres_url,
    )

    scheduler_config = SchedulerConfig(  # 构造调度配置数据类实例
        cron_expression=cron_expression,
    )

    return Settings(  # 返回聚合后的 Settings 对象
        openai_api_key=openai_api_key,
        database=database_config,
        scheduler=scheduler_config,
        timezone=timezone,
    )


settings = get_settings()  # 模块级别创建配置实例，供其他模块直接引用
