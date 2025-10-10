"""调度数据库迁移脚本，负责创建表结构与索引。"""  # 模块中文说明

from __future__ import annotations  # 启用未来注解语法

from contextlib import contextmanager  # 提供上下文管理器工具

from sqlalchemy import create_engine  # 创建数据库引擎
from sqlalchemy.orm import sessionmaker  # 构建 Session 工厂

from config.settings import settings  # 引入全局配置
from app.db.models_sched import SchedBase  # 导入调度 ORM 元数据
from app.utils.logger import get_logger  # 日志工具

LOGGER = get_logger(__name__)  # 初始化日志记录器


def get_sched_engine():  # 定义引擎创建函数
    """根据配置创建调度数据库引擎。"""  # 函数中文说明

    LOGGER.info("创建调度数据库引擎 url=%s", settings.sched_db_url)  # 记录调度库 URL
    return create_engine(settings.sched_db_url, future=True, echo=False)  # 返回 SQLAlchemy 引擎


SessionSched = sessionmaker(bind=get_sched_engine())  # 初始化调度 Session 工厂


@contextmanager
def sched_session_scope():  # 定义上下文管理器封装事务
    """提供 with 调用的 Session 生命周期管理。"""  # 函数中文说明

    session = SessionSched()  # 创建 Session
    try:  # 捕获业务异常
        yield session  # 将 Session 暴露给调用方
        session.commit()  # 正常结束提交事务
    except Exception:  # noqa: BLE001  # 捕获所有异常
        session.rollback()  # 发生异常时回滚
        raise  # 将异常继续抛出
    finally:  # 无论如何都执行
        session.close()  # 关闭 Session 释放连接


def run_migrations() -> None:  # 定义迁移主函数
    """创建调度数据库表结构，确保幂等。"""  # 函数中文说明

    engine = get_sched_engine()  # 获取引擎
    LOGGER.info("创建调度 ORM 元数据表数量=%s", len(SchedBase.metadata.tables))  # 打印表数量
    with engine.begin() as connection:  # 开启事务
        SchedBase.metadata.create_all(connection)  # 创建全部表
    LOGGER.info("调度数据库迁移完成")  # 记录完成日志


if __name__ == "__main__":  # 支持直接执行脚本
    run_migrations()  # 调用迁移函数
