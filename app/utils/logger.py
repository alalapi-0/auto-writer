# -*- coding: utf-8 -*-  # 指定 UTF-8 编码，确保中文注释兼容
"""统一日志模块，提供彩色控制台与按日滚动文件输出。"""  # 模块文档说明

from __future__ import annotations  # 启用未来注解，提升类型兼容性

import logging  # 引入标准日志库
import sys  # 访问标准输出流
from logging.handlers import TimedRotatingFileHandler  # 提供按时间滚动的文件处理器
from pathlib import Path  # 统一处理路径
from typing import Dict  # 类型注解字典

from config.settings import LOG_DIR, LOG_LEVEL  # 导入日志目录和级别配置

_COLOR_MAP = {  # 定义日志级别到 ANSI 颜色的映射表
    "DEBUG": "\033[36m",  # 调试级别使用青色
    "INFO": "\033[32m",  # 信息级别使用绿色
    "WARNING": "\033[33m",  # 警告级别使用黄色
    "ERROR": "\033[31m",  # 错误级别使用红色
}  # 映射结束
_RESET = "\033[0m"  # 定义颜色重置码

_LOGGER_CACHE: Dict[str, logging.Logger] = {}  # 使用缓存避免重复创建处理器


class _ColorFormatter(logging.Formatter):  # 自定义格式化器以输出彩色日志
    """在控制台输出中注入颜色信息。"""  # 类文档说明

    def format(self, record: logging.LogRecord) -> str:  # 重写 format 方法
        level_name = record.levelname.upper()  # 获取大写日志级别
        color = _COLOR_MAP.get(level_name, "")  # 根据级别选择颜色
        prefix = f"{color}" if color else ""  # 构造颜色前缀
        suffix = _RESET if color else ""  # 构造颜色重置码
        message = super().format(record)  # 调用基类生成基础格式
        return f"{prefix}{message}{suffix}"  # 返回带颜色的最终字符串


def _create_console_handler() -> logging.Handler:  # 构造控制台处理器
    """创建输出到标准输出的日志处理器。"""  # 函数说明

    console_handler = logging.StreamHandler(stream=sys.stdout)  # 输出到标准输出
    formatter = _ColorFormatter("%(asctime)s %(levelname)s %(name)s %(message)s")  # 定义输出格式
    console_handler.setFormatter(formatter)  # 绑定格式化器
    return console_handler  # 返回处理器实例


def _create_file_handler(log_dir: Path) -> logging.Handler | None:  # 构造文件处理器
    """尝试创建按日滚动的文件处理器，失败时返回 None。"""  # 函数说明

    try:  # 捕获目录或文件创建异常
        log_dir.mkdir(parents=True, exist_ok=True)  # 确保日志目录存在
        log_path = log_dir / "autowriter.log"  # 定义基准日志文件
        handler = TimedRotatingFileHandler(  # 创建按日滚动处理器
            filename=log_path,  # 指定日志文件路径
            when="midnight",  # 每日零点滚动
            backupCount=14,  # 保留最近两周日志
            encoding="utf-8",  # 指定编码
        )  # 处理器创建结束
        handler.suffix = "%Y-%m-%d.log"  # 设置滚动文件命名后缀，生成 YYYY-MM-DD.log
        handler.namer = lambda name: str(Path(LOG_DIR) / Path(name).name.replace("autowriter.log.", ""))  # 自定义命名将文件移至日志目录
        formatter = logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")  # 定义文件格式
        handler.setFormatter(formatter)  # 绑定格式化器
        return handler  # 返回文件处理器
    except Exception:  # noqa: BLE001  # 捕获所有异常并静默降级
        return None  # 出现异常时返回 None 以降级为纯控制台日志


def get_logger(name: str) -> logging.Logger:  # 对外提供获取日志记录器的函数
    """返回带彩色控制台与文件输出的 logger。"""  # 函数说明

    if name in _LOGGER_CACHE:  # 如果缓存中已有记录器
        return _LOGGER_CACHE[name]  # 直接返回缓存实例

    logger = logging.getLogger(name)  # 获取或创建记录器
    logger.setLevel(getattr(logging, LOG_LEVEL, logging.INFO))  # 根据配置设置日志级别
    logger.handlers.clear()  # 清空可能存在的旧处理器，避免重复输出
    logger.propagate = False  # 阻止向根记录器传播

    console_handler = _create_console_handler()  # 创建控制台处理器
    logger.addHandler(console_handler)  # 添加控制台处理器

    file_handler = _create_file_handler(Path(LOG_DIR))  # 尝试创建文件处理器
    if file_handler is not None:  # 如果文件处理器创建成功
        logger.addHandler(file_handler)  # 添加文件处理器

    _LOGGER_CACHE[name] = logger  # 将记录器缓存以复用
    return logger  # 返回配置好的记录器
