"""任务分发队列的业务操作封装。"""  # 模块中文说明

from __future__ import annotations  # 启用未来注解语法

import json  # 用于序列化 payload
import shutil  # 文件移动辅助
from datetime import datetime, timedelta  # 时间运算
from pathlib import Path  # 路径操作
from typing import Any, Dict, List  # 类型提示

from sqlalchemy import and_, func, or_  # 使用 SQL 表达式与布尔组合

from config.settings import settings  # 引入配置
from app.db.migrate_sched import sched_session_scope  # 调度库会话
from app.db.models_sched import Heartbeat, JobRun, TaskQueue  # ORM 模型
from app.utils.logger import get_logger  # 日志工具
from .store import dispatch_session_scope  # 分发库会话
from app.telemetry.client import emit_metric  # 指标事件上报
from app.telemetry.metrics import inc_run, observe_latency  # Prometheus 指标

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
                .filter(
                    or_(
                        TaskQueue.status == "pending",
                        and_(
                            TaskQueue.status == "leased",
                            TaskQueue.lease_until.isnot(None),
                            TaskQueue.lease_until < now,
                        ),
                    )
                )
                .filter(TaskQueue.available_at <= now)
                .order_by(TaskQueue.priority.desc(), TaskQueue.id.asc())
                .first()
            )
            if candidate is None:  # 无可用任务
                break  # 结束循环
            original_status = candidate.status  # 记录原始状态
            update_payload = {  # 构造更新字段
                TaskQueue.status: "leased",
                TaskQueue.lease_by: agent_name,
                TaskQueue.lease_until: now + ttl,
            }
            if original_status != "leased":  # 原状态非 leased 才累加尝试次数
                update_payload[TaskQueue.attempts] = TaskQueue.attempts + 1  # 增加尝试计数
            updated = (  # 使用条件更新确保状态竞争安全
                session.query(TaskQueue)
                .filter(TaskQueue.id == candidate.id)
                .filter(TaskQueue.status == original_status)
                .filter(
                    or_(
                        TaskQueue.status == "pending",
                        TaskQueue.lease_until.is_(None),
                        TaskQueue.lease_until < now,
                    )
                )
                .update(
                    update_payload,
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
        emit_metric("dispatch", "task_success", 1, profile_id=task.profile_id)  # 记录任务成功指标
        if task.created_at:  # 若记录了入队时间
            duration = (now - task.created_at).total_seconds()  # 计算执行耗时
            observe_latency(str(task.profile_id), duration)  # 写入 Prometheus 耗时
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
            quarantine_dir = _move_task_drafts_to_quarantine(task, error)  # 尝试隔离草稿
            emit_metric("dispatch", "task_dead", 1, profile_id=task.profile_id)  # 上报死亡指标
            if quarantine_dir:  # 若生成隔离目录
                LOGGER.error("任务达到重试上限并已隔离 task_id=%s dir=%s", task_id, quarantine_dir)  # 记录隔离信息
            else:
                LOGGER.error("任务达到重试上限 task_id=%s error=%s", task_id, error)  # 记录错误
        else:  # 仍可重试
            task.status = "pending"  # 回退为待处理
            task.available_at = now + backoff  # 设置退避时间
            _mark_job_retrying(task, error)  # 更新 JobRun 状态
            emit_metric("dispatch", "task_retry", 1, profile_id=task.profile_id)  # 上报重试指标
            LOGGER.warning("任务失败重试 task_id=%s next=%s", task_id, task.available_at)  # 记录警告
        if task.created_at:  # 若记录了入队时间
            duration = (now - task.created_at).total_seconds()  # 计算耗时
            observe_latency(str(task.profile_id), duration)  # 记录耗时
        emit_metric("dispatch", "task_failure", 1, profile_id=task.profile_id)  # 上报失败指标
        session.flush()  # 刷新持久化
        return task  # 返回任务


def _move_task_drafts_to_quarantine(task: TaskQueue, error: str) -> str | None:
    """将与任务关联的草稿目录移动至隔离区并返回隔离路径。"""  # 中文说明

    try:
        payload = json.loads(task.payload_json)  # 解析任务负载
    except json.JSONDecodeError:
        payload = {}  # 解析失败时使用空字典
    run_date_raw = str(payload.get("run_date") or _utcnow().date().isoformat())  # 解析运行日期
    day_token = run_date_raw.replace("-", "")  # 统一目录格式
    quarantine_root = Path(settings.outbox_quarantine_dir).expanduser() / day_token  # 构造隔离目录
    quarantine_root.mkdir(parents=True, exist_ok=True)  # 确保目录存在
    candidate_paths: set[str] = set()  # 准备候选目录集合
    for key in ("draft_dirs", "out_dirs", "quarantine_dirs"):  # 遍历常见字段
        value = payload.get(key)  # 读取值
        if isinstance(value, str):  # 单个路径
            candidate_paths.add(value)
        elif isinstance(value, list):  # 列表路径
            candidate_paths.update(str(item) for item in value if isinstance(item, str))
    dispatch_cfg = payload.get("dispatch", {})  # 读取 dispatch 配置
    if isinstance(dispatch_cfg, dict):  # 确保为字典
        extra_dirs = dispatch_cfg.get("draft_dirs")  # 额外目录提示
        if isinstance(extra_dirs, list):  # 若为列表
            candidate_paths.update(str(item) for item in extra_dirs if isinstance(item, str))
        platforms = dispatch_cfg.get("platforms") or settings.delivery_enabled_platforms  # 解析平台列表
    else:
        platforms = settings.delivery_enabled_platforms  # 回退到全局配置
    for platform in platforms:  # 遍历平台推断当日目录
        base = Path(settings.outbox_dir).expanduser() / str(platform) / day_token  # 计算平台当日目录
        if base.exists():  # 目录存在时加入候选
            candidate_paths.add(str(base))
    moved_paths: list[str] = []  # 记录实际移动的目录
    for path_str in sorted(candidate_paths):  # 遍历候选目录
        path_obj = Path(path_str).expanduser()  # 展开用户目录
        if not path_obj.exists():  # 路径不存在则跳过
            continue
        target = quarantine_root / f"{path_obj.name}-{task.id}"  # 构造目标路径
        counter = 1  # 初始化重名计数
        while target.exists():  # 若目标已存在
            target = quarantine_root / f"{path_obj.name}-{task.id}-{counter}"  # 叠加计数后重试
            counter += 1  # 自增计数
        try:
            shutil.move(str(path_obj), str(target))  # 执行移动
            moved_paths.append(str(target))  # 记录成功路径
        except Exception as exc:  # noqa: BLE001  # 捕获移动异常
            LOGGER.warning("草稿隔离失败 path=%s error=%s", path_obj, exc)  # 记录警告
    manifest = {  # 构造隔离清单
        "task_id": task.id,
        "profile_id": task.profile_id,
        "error": error,
        "payload": payload,
        "moved": moved_paths,
    }
    manifest_path = quarantine_root / f"task_{task.id}.json"  # 清单文件路径
    try:
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")  # 写入清单
    except Exception as exc:  # noqa: BLE001
        LOGGER.warning("写入隔离清单失败 path=%s error=%s", manifest_path, exc)  # 记录警告
    payload["quarantine_dir"] = str(quarantine_root)  # 将隔离目录回写到 payload
    payload["quarantined_paths"] = moved_paths  # 记录已移动路径
    task.payload_json = json.dumps(payload, ensure_ascii=False)  # 更新任务负载
    return str(quarantine_root) if moved_paths else None  # 若有移动则返回目录


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
        profile_label = (
            job_run.profile.name if getattr(job_run, "profile", None) and getattr(job_run.profile, "name", None) else str(job_run.profile_id)
        )  # 决定指标标签
        if success:  # 根据结果写入状态
            job_run.status = "success"
            job_run.error = None
            emit_metric("dispatch", "job_success", 1, profile_id=job_run.profile_id)  # 上报成功指标
            inc_run("success", profile_label)  # Prometheus 记录成功
        else:
            job_run.status = "failed"
            job_run.error = error_msg
            emit_metric("dispatch", "job_failed", 1, profile_id=job_run.profile_id)  # 上报失败指标
            inc_run("failed", profile_label)  # Prometheus 记录失败
        if job_run.started_at:  # 若存在开始时间
            duration = (finished_at - job_run.started_at).total_seconds()  # 计算耗时
            if duration > 0:  # 确保耗时为正
                observe_latency(profile_label, duration)  # 记录耗时直方图
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

    now = _utcnow()  # 当前时间
    with dispatch_session_scope() as session:  # 打开分发库
        rows = session.query(Heartbeat).order_by(Heartbeat.last_seen_at.desc()).all()  # 查询全部
        result: List[Dict[str, Any]] = []  # 准备返回列表
        for row in rows:  # 遍历心跳记录
            meta = json.loads(row.meta_json) if row.meta_json else {}  # 解析元信息
            poll = float(meta.get("poll_interval") or settings.job_retry_backoff_sec)  # 获取 Worker 轮询间隔
            threshold = max(poll * 2, float(settings.job_heartbeat_ttl_sec))  # 计算允许的离线阈值
            elapsed = (now - row.last_seen_at).total_seconds()  # 计算离线秒数
            result.append(  # 组装记录
                {
                    "agent_name": row.agent_name,
                    "last_seen_at": row.last_seen_at.isoformat(),
                    "meta": meta,
                    "is_stale": elapsed > threshold,
                }
            )
    return result  # 返回心跳列表


def list_dead_letters() -> List[Dict[str, Any]]:  # 列出死亡任务
    """返回死亡任务摘要，供 Dashboard 展示死信箱。"""  # 中文说明

    with dispatch_session_scope() as session:  # 打开分发库
        rows = (  # 查询死亡任务
            session.query(TaskQueue)
            .filter(TaskQueue.status == "dead")
            .order_by(TaskQueue.id.desc())
            .all()
        )
    dead_items: List[Dict[str, Any]] = []  # 准备结果列表
    for row in rows:  # 遍历死亡任务
        try:
            payload = json.loads(row.payload_json)  # 解析 payload
        except json.JSONDecodeError:
            payload = {}  # 解析失败时使用空字典
        dead_items.append(  # 组装记录
            {
                "task_id": row.id,
                "profile_id": row.profile_id,
                "attempts": row.attempts,
                "error": row.last_error,
                "quarantine_dir": payload.get("quarantine_dir"),
            }
        )
    return dead_items  # 返回死信任务
