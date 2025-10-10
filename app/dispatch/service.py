"""任务分发队列的业务操作封装。"""  # 模块中文说明

from __future__ import annotations  # 启用未来注解语法

import json  # 用于序列化 payload
from datetime import datetime, timedelta  # 时间运算
from typing import Any, Dict, List  # 类型提示

from sqlalchemy import func  # 使用 SQL 表达式

from config.settings import settings  # 引入配置
from app.db.migrate_sched import sched_session_scope  # 调度库会话
from app.db.models_sched import Heartbeat, JobRun, TaskQueue  # ORM 模型
from app.utils.logger import get_logger  # 日志工具
from .store import dispatch_session_scope  # 分发库会话

LOGGER = get_logger(__name__)  # 初始化日志记录器


def _utcnow() -> datetime:  # 内部统一获取当前 UTC 时间
    """返回当前的 UTC 时间，确保数据库时序一致。"""  # 中文说明

    return datetime.utcnow()  # 使用标准库获取朴素 UTC


def enqueue_task(
    profile_id: int,  # Profile ID
    payload: Dict[str, Any],  # 任务负载
    priority: int = 0,  # 任务优先级
    available_at: datetime | None = None,  # 可领取时间
    max_attempts: int | None = None,  # 最大尝试次数
    idempotency_key: str | None = None,  # 幂等键
) -> TaskQueue:
    """创建队列任务，若提供幂等键则返回已有记录。"""  # 中文说明

    if available_at is None:  # 若未指定可领取时间
        available_at = _utcnow()  # 默认立即可领取
    if max_attempts is None:  # 若未指定最大尝试次数
        max_attempts = settings.job_max_retries  # 使用配置默认值
    with dispatch_session_scope() as session:  # 打开分发库会话
        if idempotency_key:  # 若提供幂等键
            existing = (  # 查询是否已存在任务
                session.query(TaskQueue)
                .filter(TaskQueue.idempotency_key == idempotency_key)
                .one_or_none()
            )
            if existing:  # 若已存在
                LOGGER.info("命中幂等键 idempotency_key=%s task_id=%s", idempotency_key, existing.id)  # 记录日志
                return existing  # 直接返回
        record = TaskQueue(  # 创建任务对象
            profile_id=profile_id,
            payload_json=json.dumps(payload, ensure_ascii=False),
            available_at=available_at,
            priority=priority,
            status="pending",
            max_attempts=max_attempts,
            idempotency_key=idempotency_key,
        )
        session.add(record)  # 加入会话
        session.flush()  # 刷新以获取 ID
        LOGGER.info("任务入队 task_id=%s profile_id=%s", record.id, profile_id)  # 记录入队日志
        return record  # 返回任务


def lease_tasks(agent_name: str, limit: int) -> List[TaskQueue]:  # 租约任务
    """按照优先级为指定 Worker 分配任务。"""  # 中文说明

    now = _utcnow()  # 当前时间
    leased: List[TaskQueue] = []  # 准备返回列表
    ttl = timedelta(seconds=settings.job_heartbeat_ttl_sec)  # 计算租约过期时间
    with dispatch_session_scope() as session:  # 打开分发库会话
        for _ in range(limit):  # 最多尝试 limit 次
            candidate = (  # 查询符合条件的任务
                session.query(TaskQueue)
                .filter(TaskQueue.status == "pending")
                .filter(TaskQueue.available_at <= now)
                .order_by(TaskQueue.priority.desc(), TaskQueue.id.asc())
                .first()
            )
            if candidate is None:  # 无可用任务
                break  # 结束循环
            updated = (  # 使用条件更新确保状态竞争安全
                session.query(TaskQueue)
                .filter(TaskQueue.id == candidate.id)
                .filter(TaskQueue.status == "pending")
                .update(
                    {
                        TaskQueue.status: "leased",
                        TaskQueue.lease_by: agent_name,
                        TaskQueue.lease_until: now + ttl,
                        TaskQueue.attempts: TaskQueue.attempts + 1,
                    },
                    synchronize_session=False,
                )
            )
            if not updated:  # 若更新失败说明被竞争
                session.rollback()  # 回滚当前事务
                continue  # 重试下一轮
            session.refresh(candidate)  # 刷新实体
            leased.append(candidate)  # 收集任务
            _mark_job_running(candidate, agent_name)  # 同步 JobRun 状态
    return leased  # 返回租约结果


def _mark_job_running(task: TaskQueue, agent_name: str) -> None:  # 标记 JobRun 正在执行
    """当任务被租约时更新 JobRun 状态与开始时间。"""  # 中文说明

    try:
        payload = json.loads(task.payload_json)  # 解析 payload
    except json.JSONDecodeError:  # 解析失败
        LOGGER.warning("任务 payload 非法 task_id=%s", task.id)  # 记录告警
        return  # 无法更新 JobRun
    job_run_id = payload.get("job_run_id")  # 读取 JobRun ID
    if not job_run_id:  # 未提供则跳过
        return  # 不更新
    with sched_session_scope() as session:  # 打开调度库
        job_run = session.query(JobRun).filter(JobRun.id == job_run_id).one_or_none()  # 查询 JobRun
        if not job_run:  # 未找到
            LOGGER.warning("JobRun 不存在 job_run_id=%s", job_run_id)  # 记录警告
            return  # 直接返回
        job_run.status = "running"  # 更新状态
        job_run.started_at = _utcnow()  # 重置开始时间
        job_run.finished_at = None  # 清空结束时间
        job_run.error = None  # 清除错误
        LOGGER.info("JobRun 开始执行 job_run_id=%s agent=%s", job_run_id, agent_name)  # 记录日志


def complete_task(
    task_id: int,  # 任务 ID
    agent_name: str,  # Worker 名称
    result: Dict[str, Any],  # 执行结果
) -> TaskQueue:
    """将任务标记为完成并写回运行结果。"""  # 中文说明

    now = _utcnow()  # 当前时间
    with dispatch_session_scope() as session:  # 打开分发库
        task = session.query(TaskQueue).filter(TaskQueue.id == task_id).one_or_none()  # 查询任务
        if task is None:  # 未找到任务
            raise ValueError(f"task {task_id} not found")  # 抛出异常
        if task.status != "leased" or task.lease_by != agent_name:  # 校验租约归属
            raise ValueError("task not leased by agent")  # 抛出异常
        task.status = "done"  # 标记为完成
        task.lease_by = None  # 清理租约持有者
        task.lease_until = None  # 清理租约到期
        session.flush()  # 刷新持久化
        _finalize_job_run(task, result, now, success=True)  # 更新 JobRun
        LOGGER.info("任务完成 task_id=%s agent=%s", task_id, agent_name)  # 记录日志
        return task  # 返回任务


def fail_task(
    task_id: int,  # 任务 ID
    agent_name: str,  # Worker 名称
    error: str,  # 错误信息
) -> TaskQueue:
    """任务失败后根据重试策略重新入队或标记死亡。"""  # 中文说明

    now = _utcnow()  # 当前时间
    backoff = timedelta(seconds=settings.job_retry_backoff_sec)  # 重试退避
    with dispatch_session_scope() as session:  # 打开分发库
        task = session.query(TaskQueue).filter(TaskQueue.id == task_id).one_or_none()  # 查询任务
        if task is None:  # 未找到
            raise ValueError(f"task {task_id} not found")  # 抛出异常
        if task.status != "leased" or task.lease_by != agent_name:  # 校验租约归属
            raise ValueError("task not leased by agent")  # 抛出异常
        task.lease_by = None  # 清理租约
        task.lease_until = None  # 清空到期时间
        task.last_error = error  # 记录错误
        if task.attempts >= task.max_attempts:  # 超过最大次数
            task.status = "dead"  # 标记死亡
            _finalize_job_run(task, {"error": error}, now, success=False)  # 更新 JobRun 失败
            LOGGER.error("任务达到重试上限 task_id=%s error=%s", task_id, error)  # 记录错误
        else:  # 仍可重试
            task.status = "pending"  # 回退为待处理
            task.available_at = now + backoff  # 设置退避时间
            _mark_job_retrying(task, error)  # 更新 JobRun 状态
            LOGGER.warning("任务失败重试 task_id=%s next=%s", task_id, task.available_at)  # 记录警告
        session.flush()  # 刷新持久化
        return task  # 返回任务


def _finalize_job_run(task: TaskQueue, result: Dict[str, Any], finished_at: datetime, success: bool) -> None:
    """根据任务执行结果更新 JobRun。"""  # 中文说明

    try:
        payload = json.loads(task.payload_json)  # 解析 payload
    except json.JSONDecodeError:
        LOGGER.warning("任务 payload 非法，跳过 JobRun 更新 task_id=%s", task.id)  # 记录警告
        return
    job_run_id = result.get("job_run_id") or payload.get("job_run_id")  # 读取 JobRun ID
    if not job_run_id:  # 若未提供
        return  # 直接返回
    emitted = int(result.get("emitted_articles", 0) or 0)  # 解析生成数量
    success_count = int(result.get("delivered_success", 0) or 0)  # 成功投递数
    failed_count = int(result.get("delivered_failed", 0) or 0)  # 失败投递数
    error_msg = result.get("error")  # 错误信息
    with sched_session_scope() as session:  # 打开调度库
        job_run = session.query(JobRun).filter(JobRun.id == job_run_id).one_or_none()  # 查询记录
        if not job_run:
            LOGGER.warning("JobRun 不存在 job_run_id=%s", job_run_id)  # 记录警告
            return
        job_run.finished_at = finished_at  # 写入结束时间
        job_run.emitted_articles = emitted  # 写入生成数量
        job_run.delivered_success = success_count  # 写入成功投递
        job_run.delivered_failed = failed_count  # 写入失败投递
        if success:  # 根据结果写入状态
            job_run.status = "success"
            job_run.error = None
        else:
            job_run.status = "failed"
            job_run.error = error_msg
        LOGGER.info(
            "JobRun 完成更新 job_run_id=%s status=%s", job_run_id, job_run.status
        )  # 记录日志


def _mark_job_retrying(task: TaskQueue, error: str) -> None:  # 更新 JobRun 为重试中
    """当任务等待重试时记录当前错误信息。"""  # 中文说明

    try:
        payload = json.loads(task.payload_json)  # 解析 payload
    except json.JSONDecodeError:
        return  # 无法解析直接返回
    job_run_id = payload.get("job_run_id")  # 读取 JobRun
    if not job_run_id:
        return  # 无 JobRun 直接返回
    with sched_session_scope() as session:  # 打开调度库
        job_run = session.query(JobRun).filter(JobRun.id == job_run_id).one_or_none()  # 查询记录
        if not job_run:
            return  # 未找到
        job_run.status = "retrying"  # 更新状态
        job_run.error = error  # 写入错误


def record_heartbeat(agent_name: str, meta: Dict[str, Any] | None) -> None:  # 记录心跳
    """写入或更新 Worker 心跳时间。"""  # 中文说明

    with dispatch_session_scope() as session:  # 打开分发库
        record = session.query(Heartbeat).filter(Heartbeat.agent_name == agent_name).one_or_none()  # 查询
        meta_json = json.dumps(meta or {}, ensure_ascii=False)  # 序列化元信息
        if record is None:  # 若不存在
            record = Heartbeat(agent_name=agent_name, last_seen_at=_utcnow(), meta_json=meta_json)  # 创建记录
            session.add(record)  # 添加
        else:  # 已存在
            record.last_seen_at = _utcnow()  # 更新心跳时间
            record.meta_json = meta_json  # 更新元数据


def get_queue_stats() -> Dict[str, int]:  # 队列统计
    """统计队列内各状态数量。"""  # 中文说明

    with dispatch_session_scope() as session:  # 打开分发库
        rows = (
            session.query(TaskQueue.status, func.count(TaskQueue.id))
            .group_by(TaskQueue.status)
            .all()
        )  # 聚合统计
    return {status: count for status, count in rows}  # 转换为字典


def list_heartbeats() -> List[Dict[str, Any]]:  # 列出心跳信息
    """返回所有 Worker 心跳记录。"""  # 中文说明

    with dispatch_session_scope() as session:  # 打开分发库
        rows = session.query(Heartbeat).order_by(Heartbeat.last_seen_at.desc()).all()  # 查询全部
        return [
            {
                "agent_name": row.agent_name,
                "last_seen_at": row.last_seen_at.isoformat(),
                "meta": json.loads(row.meta_json) if row.meta_json else {},
            }
            for row in rows
        ]  # 序列化结果
