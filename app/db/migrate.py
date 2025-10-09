"""数据库迁移与初始化脚本。

职责：
* 创建 SQLAlchemy 引擎与 Session 工厂；
* 执行 ORM 元数据创建；
* 运行 ``schema.sql`` 中的手写 SQL，确保约束一致。
"""

from __future__ import annotations

from sqlalchemy import create_engine, text  # 创建数据库连接与执行原生 SQL
from sqlalchemy.orm import sessionmaker  # 创建 Session 工厂

from config.settings import settings, BASE_DIR  # 加载配置与项目根目录
from app.db.models import Base  # 导入 ORM 元数据
from app.utils.logger import get_logger  # 引入统一日志模块

SCHEMA_PATH = BASE_DIR / "app" / "db" / "schema.sql"  # SQL 脚本路径

LOGGER = get_logger(__name__)  # 初始化模块级日志记录器


def get_engine():
    """根据配置创建数据库引擎。"""

    LOGGER.info("创建数据库引擎 url=%s", settings.database.url)  # 记录引擎创建意图
    return create_engine(  # 返回 SQLAlchemy 引擎
        settings.database.url,  # 使用配置中的数据库 URL
        echo=False,  # 关闭 SQL 回显
        future=True,  # 启用 2.0 风格
    )


SessionLocal = sessionmaker(bind=get_engine())  # 配置 Session 工厂


def apply_sql_schema() -> None:
    """执行 schema.sql 文件以初始化数据库结构。"""

    engine = get_engine()  # 创建引擎
    LOGGER.info("应用 schema SQL path=%s", str(SCHEMA_PATH))  # 记录脚本路径
    with engine.begin() as connection:  # 使用事务上下文
        sql_commands = SCHEMA_PATH.read_text(encoding="utf-8")  # 读取 SQL 脚本
        for statement in filter(None, (stmt.strip() for stmt in sql_commands.split(";"))):  # 遍历语句
            LOGGER.debug("执行 schema 语句 snippet=%s", statement[:60])  # 记录执行片段
            connection.execute(text(statement))  # 执行 SQL
    LOGGER.info("schema SQL 执行完成")  # 记录完成


def init_database() -> None:
    """初始化数据库，包含 ORM 创建与 SQL 脚本执行。"""

    try:  # 捕获初始化过程中的异常
        engine = get_engine()  # 创建引擎
        LOGGER.info("创建 ORM 元数据表 tables=%d", len(Base.metadata.tables))  # 记录表数量
        Base.metadata.create_all(engine)  # 创建 ORM 定义的表
        apply_sql_schema()  # 执行 schema.sql
        LOGGER.info("数据库初始化完成")  # 记录成功
    except Exception as exc:  # noqa: BLE001  # 捕获所有异常
        LOGGER.exception("数据库初始化失败 error=%s", str(exc))  # 记录异常详情
        raise  # 继续抛出异常供上层处理


if __name__ == "__main__":
    init_database()
