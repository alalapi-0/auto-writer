# -*- coding: utf-8 -*-  # 指定 UTF-8 编码
"""集成测试级别的公共夹具，提供临时数据库与目录。"""  # 模块说明

from __future__ import annotations  # 启用未来注解语法

from pathlib import Path  # 处理路径
from typing import Dict, Generator  # 类型提示

import pytest  # 测试框架
from sqlalchemy import create_engine, text  # 创建引擎与执行 SQL

from app.db.migrate import SessionLocal, init_database, get_engine  # 导入会话工厂与初始化函数
from config.settings import settings  # 全局配置


@pytest.fixture
def temp_settings(tmp_path: Path) -> Generator[Dict[str, Path], None, None]:  # 定义临时环境夹具
    """创建隔离的 SQLite 数据库与输出目录，并在测试后恢复配置。"""  # 函数说明

    db_path = tmp_path / "autowriter_test.db"  # 构造 SQLite 文件路径
    db_url = f"sqlite:///{db_path}"  # 生成连接字符串
    outbox_dir = tmp_path / "outbox"  # 构造 outbox 目录
    logs_dir = tmp_path / "logs"  # 构造日志目录
    exports_dir = tmp_path / "exports"  # 构造导出目录
    engine = create_engine(db_url, future=True)  # 创建 SQLAlchemy 引擎

    orig_db_url = settings.database.url  # 记录原数据库 URL
    orig_sqlite = settings.sqlite_url  # 记录原 SQLite URL
    orig_outbox = settings.outbox_dir  # 记录原 outbox
    orig_logs = settings.logs_dir  # 记录原日志目录
    orig_exports = settings.exports_dir  # 记录原导出目录
    orig_platforms = list(settings.delivery_enabled_platforms)  # 记录原启用平台
    orig_retry_base = settings.retry_base_seconds  # 记录原重试基础秒数
    orig_retry_max = settings.retry_max_attempts  # 记录原最大重试次数

    settings.database.url = db_url  # 切换数据库 URL
    settings.sqlite_url = db_url  # 切换 SQLite URL
    settings.outbox_dir = str(outbox_dir)  # 重定向 outbox
    settings.logs_dir = logs_dir  # 重定向日志目录
    settings.exports_dir = exports_dir  # 重定向导出目录
    settings.delivery_enabled_platforms = ["wechat_mp", "zhihu"]  # 启用两个投递平台
    settings.retry_base_seconds = 1  # 缩短重试间隔便于测试
    settings.retry_max_attempts = 3  # 设置较小的最大重试次数

    SessionLocal.configure(bind=engine)  # 重新绑定 Session 工厂
    init_database()  # 初始化数据库结构

    with engine.begin() as connection:  # 创建主题表以支持测试
        connection.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS psychology_themes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    psychology_keyword TEXT NOT NULL,
                    psychology_definition TEXT,
                    character_name TEXT,
                    show_name TEXT,
                    locked_by_run_id TEXT,
                    locked_at TEXT,
                    used INTEGER DEFAULT 0,
                    used_at TEXT,
                    used_by_run_id TEXT
                )
                """
            )
        )

    try:  # 向调用方提供配置
        yield {
            "db_path": db_path,
            "engine": engine,
            "outbox": outbox_dir,
            "logs": logs_dir,
            "exports": exports_dir,
        }
    finally:  # 恢复全局状态
        settings.database.url = orig_db_url  # 恢复数据库 URL
        settings.sqlite_url = orig_sqlite  # 恢复 SQLite URL
        settings.outbox_dir = orig_outbox  # 恢复 outbox
        settings.logs_dir = orig_logs  # 恢复日志目录
        settings.exports_dir = orig_exports  # 恢复导出目录
        settings.delivery_enabled_platforms = orig_platforms  # 恢复平台列表
        settings.retry_base_seconds = orig_retry_base  # 恢复重试基础秒数
        settings.retry_max_attempts = orig_retry_max  # 恢复最大重试次数
        SessionLocal.configure(bind=get_engine())  # 重新绑定默认引擎
        engine.dispose()  # 释放测试引擎


def pytest_configure(config: pytest.Config) -> None:  # 注册集成测试标记
    """为 pytest 添加 integration 标记描述以消除警告。"""  # 函数说明

    config.addinivalue_line("markers", "integration: 标记端到端集成测试")  # 注册标记
