"""调度控制 API，供 Dashboard 调用。"""  # 模块说明

from __future__ import annotations  # 启用未来注解语法

from datetime import datetime  # 处理时间

from app.db.migrate_sched import sched_session_scope  # 调度库 Session
from app.db.models_sched import Schedule  # ORM 模型
from app.scheduler.service import run_profile  # 调度函数
from app.utils.logger import get_logger  # 日志工具

LOGGER = get_logger(__name__)  # 初始化日志


def list_schedules() -> list[dict]:  # 列出调度
    """返回所有调度的简要信息。"""  # 中文说明

    with sched_session_scope() as session:  # 打开 Session
        rows = session.query(Schedule).all()  # 查询全部
        data = []  # 准备返回列表
        for row in rows:  # 遍历记录
            data.append(
                {
                    "id": row.id,
                    "profile_id": row.profile_id,
                    "cron": row.cron_expr,
                    "paused": row.is_paused,
                    "next_run_at": row.next_run_at.isoformat() if row.next_run_at else None,
                }
            )  # 填充数据
        return data  # 返回结果


def pause_schedule(schedule_id: int) -> None:  # 暂停调度
    """根据调度 ID 将任务置为暂停状态。"""  # 中文说明

    with sched_session_scope() as session:  # 打开 Session
        row = session.query(Schedule).filter(Schedule.id == schedule_id).one_or_none()  # 查询记录
        if row is None:  # 未找到
            raise ValueError("调度不存在")  # 抛出异常
        row.is_paused = True  # 设置暂停
        LOGGER.info("暂停调度 id=%s", schedule_id)  # 记录日志


def resume_schedule(schedule_id: int) -> None:  # 恢复调度
    """将暂停的调度恢复并更新下一次执行时间。"""  # 中文说明

    with sched_session_scope() as session:  # 打开 Session
        row = session.query(Schedule).filter(Schedule.id == schedule_id).one_or_none()  # 查询记录
        if row is None:  # 未找到
            raise ValueError("调度不存在")  # 抛出异常
        row.is_paused = False  # 取消暂停
        row.next_run_at = datetime.utcnow()  # 重置下次运行时间
        LOGGER.info("恢复调度 id=%s", schedule_id)  # 记录日志


def run_now(profile_id: int) -> None:  # 立即执行
    """立即触发一次 Profile 运行。"""  # 中文说明

    run_profile(profile_id)  # 调用调度任务
