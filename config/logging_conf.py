"""结构化日志配置模块。

该模块在导入时立刻配置 Python logging 与 structlog，确保所有子模块
可以直接调用 ``structlog.get_logger()`` 获取 JSON 格式日志。
"""

from __future__ import annotations

import logging  # 标准库 logging
from logging.config import dictConfig  # 允许使用字典定义配置

import structlog  # 第三方结构化日志库


def setup_logging() -> None:
    """配置标准日志与 structlog 集成。"""

    timestamper = structlog.processors.TimeStamper(  # 创建时间戳处理器
        fmt="iso"  # 使用 ISO8601 格式，便于日志聚合平台解析
    )

    dictConfig(  # 使用 dictConfig 配置标准日志器
        {
            "version": 1,  # 表示配置版本，固定值
            "disable_existing_loggers": False,  # 保留其他模块已有的 logger
            "formatters": {
                "plain": {
                    "format": "%(message)s",  # 基础 formatter 输出纯文本信息
                }
            },
            "handlers": {
                "default": {
                    "class": "logging.StreamHandler",  # 使用标准输出作为日志出口
                    "formatter": "plain",  # 指定上述 formatter
                }
            },
            "root": {
                "handlers": ["default"],  # 根 logger 绑定默认 handler
                "level": "INFO",  # 设置日志级别，生产环境可改为 WARN/ERROR
            },
        }
    )

    structlog.configure(  # 配置 structlog，支持结构化日志输出
        processors=[
            structlog.processors.add_log_level,  # 添加日志级别字段
            timestamper,  # 添加时间戳字段
            structlog.processors.format_exc_info,  # 若存在异常则格式化堆栈信息
            structlog.processors.JSONRenderer(),  # 以 JSON 格式渲染日志，便于集中日志系统解析
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),  # 设定日志级别过滤
        cache_logger_on_first_use=True,  # 首次使用后缓存 logger，避免重复配置
    )


setup_logging()  # 模块导入即完成日志配置，确保日志可用
