"""调度与分发数据库会话工厂，封装连接与迁移。"""  # 模块中文说明

from __future__ import annotations  # 启用未来注解语法

from contextlib import contextmanager  # 提供上下文管理器
from pathlib import Path  # 处理路径
from typing import Iterator  # 类型提示

from sqlalchemy import create_engine  # 创建 SQLAlchemy 引擎
from sqlalchemy.orm import sessionmaker  # Session 工厂

from config.settings import settings  # 引入配置
from app.db.models_sched import Heartbeat, SchedBase, TaskQueue  # 导入 ORM 模型
from app.utils.logger import get_logger  # 日志工具

LOGGER = get_logger(__name__)  # 初始化日志记录器


def get_dispatch_engine():  # 创建分发库引擎
    """根据配置初始化分发任务数据库引擎。"""  # 中文说明

    LOGGER.debug("创建分发数据库引擎 url=%s", settings.dispatch_db_url)  # 记录调试日志
    return create_engine(settings.dispatch_db_url, future=True, echo=False)  # 返回引擎实例


# expire_on_commit=False 确保提交后 ORM 实例仍可访问字段，供 API 序列化使用
SessionDispatch = sessionmaker(bind=get_dispatch_engine(), expire_on_commit=False)  # 初始化分发 Session 工厂


@contextmanager
def dispatch_session_scope() -> Iterator:  # 分发库 Session 上下文
    """提供 with 语法的分发库会话生命周期管理。"""  # 中文说明

    session = SessionDispatch()  # 创建 Session
    try:  # 捕获异常
        yield session  # 暴露 Session 给调用方
        session.commit()  # 正常结束时提交事务
    except Exception:  # noqa: BLE001  # 捕获全部异常
        session.rollback()  # 发生异常时回滚
        raise  # 继续抛出异常
    finally:  # 无论如何执行
        session.close()  # 关闭 Session


def run_dispatch_migrations() -> None:  # 执行分发库建表
    """确保分发任务所需的表结构存在。"""  # 中文说明

    engine = get_dispatch_engine()  # 获取引擎
    SessionDispatch.configure(bind=engine)  # 重新绑定 Session 工厂
    if engine.url.get_backend_name() == "sqlite" and engine.url.database:  # 若使用本地 SQLite
        Path(engine.url.database).parent.mkdir(parents=True, exist_ok=True)  # 确保目录存在
    tables = [  # 需要创建的表列表
        SchedBase.metadata.tables[TaskQueue.__tablename__],  # 队列表
        SchedBase.metadata.tables[Heartbeat.__tablename__],  # 心跳表
    ]
    with engine.begin() as connection:  # 打开事务
        for table in tables:  # 遍历表
            LOGGER.debug("创建分发表=%s", table.name)  # 记录日志
            table.create(connection, checkfirst=True)  # 幂等创建
    LOGGER.info("分发数据库迁移完成")  # 记录完成日志
