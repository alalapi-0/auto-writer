"""数据库迁移与初始化脚本。"""

from __future__ import annotations

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from config.settings import settings, BASE_DIR
from app.db.models import Base

SCHEMA_PATH = BASE_DIR / "app" / "db" / "schema.sql"  # SQL 脚本路径


def get_engine():
    """根据配置创建数据库引擎。"""

    return create_engine(settings.database.default_url, echo=False, future=True)  # 创建 SQLAlchemy 引擎


SessionLocal = sessionmaker(bind=get_engine())  # 配置 Session 工厂


def apply_sql_schema() -> None:
    """执行 schema.sql 文件以初始化数据库结构。"""

    engine = get_engine()  # 获取数据库引擎
    with engine.begin() as connection:  # 打开事务性连接
        sql_commands = SCHEMA_PATH.read_text(encoding="utf-8")  # 读取 SQL 脚本内容
        for statement in filter(None, sql_commands.split(";")):  # 遍历每条 SQL 语句
            connection.execute(text(statement))  # 执行 SQL 语句


def init_database() -> None:
    """初始化数据库，包含 ORM 创建与 SQL 脚本执行。"""

    engine = get_engine()  # 获取数据库引擎
    Base.metadata.create_all(engine)  # 使用 ORM 元数据创建表结构
    apply_sql_schema()  # 再次执行 schema.sql 以兼容手写 SQL 约束


if __name__ == "__main__":  # 若直接执行脚本
    init_database()  # 调用初始化函数
