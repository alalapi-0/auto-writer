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

SCHEMA_PATH = BASE_DIR / "app" / "db" / "schema.sql"  # SQL 脚本路径


def get_engine():
    """根据配置创建数据库引擎。"""

    return create_engine(
        settings.database.url,
        echo=False,
        future=True,
    )


SessionLocal = sessionmaker(bind=get_engine())  # 配置 Session 工厂


def apply_sql_schema() -> None:
    """执行 schema.sql 文件以初始化数据库结构。"""

    engine = get_engine()
    with engine.begin() as connection:
        sql_commands = SCHEMA_PATH.read_text(encoding="utf-8")
        for statement in filter(None, (stmt.strip() for stmt in sql_commands.split(";"))):
            connection.execute(text(statement))


def init_database() -> None:
    """初始化数据库，包含 ORM 创建与 SQL 脚本执行。"""

    engine = get_engine()
    Base.metadata.create_all(engine)
    apply_sql_schema()


if __name__ == "__main__":
    init_database()
