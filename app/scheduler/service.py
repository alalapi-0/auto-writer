"""调度服务：负责加载 Profile、注册定时任务并执行 run_profile。"""  # 模块说明

from __future__ import annotations  # 启用未来注解语法

import threading  # 提供本地锁
from datetime import datetime, timezone  # 处理时间
from time import perf_counter  # 高精度耗时计算
from pathlib import Path  # 处理路径
from zoneinfo import ZoneInfo  # 处理时区

from apscheduler.schedulers.background import BackgroundScheduler  # 后台调度器
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore  # SQLAlchemy JobStore
from apscheduler.triggers.cron import CronTrigger  # Cron 触发器

from config.settings import settings  # 引入配置
from app.db.migrate_sched import run_migrations, sched_session_scope  # 调度数据库工具
from app.db.models_sched import JobRun, Profile, Schedule  # ORM 模型
from app.profiles.loader import sync_profiles  # Profile 同步函数
from app.telemetry.client import emit_metric  # 指标上报
from app.telemetry.metrics import (  # Prometheus 指标埋点工具
    inc_delivery,  # 记录投递结果计数
    inc_generation,  # 记录生成次数
    inc_run,  # 记录作业运行结果
    observe_latency,  # 记录作业耗时
)  # 导入结束
from app.plugins.loader import apply_filter_hooks, run_exporter_hook  # 插件 Hook
from app.utils.logger import get_logger  # 日志工具

LOGGER = get_logger(__name__)  # 初始化日志

LOCAL_TZ = ZoneInfo(settings.tz)  # 根据配置创建时区对象


def _now_local() -> datetime:  # 获取配置时区当前时间
    """返回带时区信息的当前时间，便于展示与审计。"""  # 中文说明

    return datetime.now(LOCAL_TZ)  # 依据配置时区获取时间


def _now_utc_naive() -> datetime:  # 获取朴素 UTC 时间
    """转换为 UTC 并去除 tzinfo，以兼容现有数据库列。"""  # 中文说明

    return datetime.now(timezone.utc).replace(tzinfo=None)  # 计算 UTC 时间后移除时区

_SCHEDULER: BackgroundScheduler | None = None  # 全局调度器引用
_PROFILE_LOCKS: dict[int, threading.Lock] = {}  # Profile 粒度锁


def _get_lock(profile_id: int) -> threading.Lock:  # 获取或创建 Profile 锁
    """返回指定 Profile 的互斥锁，确保同一 Profile 不并发执行。"""  # 中文说明

    if profile_id not in _PROFILE_LOCKS:  # 若锁不存在
        _PROFILE_LOCKS[profile_id] = threading.Lock()  # 创建锁
    return _PROFILE_LOCKS[profile_id]  # 返回锁


def _load_profile_yaml(yaml_path: str) -> dict:  # 读取 YAML 内容
    """从传入的 YAML 路径加载配置。"""  # 中文说明

    path = Path(yaml_path)  # 构造路径
    if not path.exists():  # 若文件不存在
        raise FileNotFoundError(f"Profile YAML 不存在: {path}")  # 抛出异常
    import yaml  # 局部导入避免顶层依赖  # 中文注释

    return yaml.safe_load(path.read_text(encoding="utf-8"))  # 使用 yaml 解析配置


def run_profile(profile_id: int) -> None:  # 供 APScheduler 调用的任务函数
    """执行单个 Profile 的生成与投递流程（示例实现）。"""  # 中文说明

    lock = _get_lock(profile_id)  # 获取锁
    start_ts = perf_counter()  # 记录任务开始的高精度时间戳
    profile_label = str(profile_id)  # 默认使用 profile_id 作为标签
    if not lock.acquire(blocking=False):  # 尝试获取锁
        LOGGER.info("Profile 仍在执行，跳过 profile_id=%s", profile_id)  # 记录提示
        return  # 直接返回
    job_id = None  # 初始化运行记录 ID
    try:  # 捕获执行异常
        with sched_session_scope() as session:  # 打开 Session
            profile = session.query(Profile).filter(Profile.id == profile_id).one_or_none()  # 查询 Profile
            if profile is None or not profile.is_enabled:  # 校验启用状态
                LOGGER.warning("Profile 不存在或已禁用 profile_id=%s", profile_id)  # 记录警告
                inc_run("skipped", profile_label)  # 记录一次跳过
                return  # 直接返回
            job = JobRun(profile_id=profile_id, status="running")  # 创建运行记录
            session.add(job)  # 添加记录
            session.flush()  # 刷新获取 ID
            job_id = job.id  # 保存 ID
            yaml_path = profile.yaml_path  # 缓存 YAML 路径
            profile_name = profile.name  # 缓存 Profile 名称
            if profile_name:  # 若存在 profile 名称
                profile_label = profile_name  # 使用更友好的标签
        profile_yaml = _load_profile_yaml(yaml_path)  # 加载 YAML 配置
        plan_payload = {"profile": profile_name, "timestamp": _now_local().isoformat()}  # 构造计划数据
        plan_payload = apply_filter_hooks("on_before_generate", plan_payload)  # 调用生成前 Hook
        article = {
            "title": f"{profile_yaml.get('name')} 自动稿件",  # 模拟生成标题
            "content": "这是一篇示例文章，用于演示调度链路。",  # 模拟正文
            "profile": profile_name,  # 记录 Profile 名称
        }
        article = apply_filter_hooks("on_after_generate", article)  # 调用生成后 Hook
        inc_generation(profile_label)  # 记录生成成功
        platforms = profile_yaml.get("delivery", {}).get("platforms", [])  # 获取投递平台
        success_count = 0  # 初始化成功计数
        for platform in platforms:  # 遍历平台
            run_exporter_hook("on_before_publish", article, platform)  # 发布前 Hook
            result = {"title": article["title"], "summary": article.get("content", "")[:50]}  # 模拟发布结果
            run_exporter_hook("on_after_publish", result, platform)  # 发布后 Hook
            success_count += 1  # 模拟成功
            emit_metric("delivery", "platform_success", 1, profile_id=profile_id, platform=platform)  # 上报指标
            inc_delivery(platform, "success")  # 记录投递成功
        emit_metric("generation", "articles_emitted", 1, profile_id=profile_id)  # 上报生成指标
        with sched_session_scope() as session:  # 再次打开 Session 更新状态
            job = session.query(JobRun).filter(JobRun.id == job_id).one()  # 获取记录
            job.status = "success"  # 标记成功
            job.finished_at = _now_utc_naive()  # 记录结束时间
            job.emitted_articles = 1  # 写入生成数量
            job.delivered_success = success_count  # 写入成功数量
            job.delivered_failed = max(0, len(platforms) - success_count)  # 写入失败数量
        inc_run("success", profile_label)  # 记录成功运行
        observe_latency(profile_label, perf_counter() - start_ts)  # 记录耗时
    except Exception as exc:  # noqa: BLE001
        LOGGER.exception("Profile 执行失败 profile_id=%s", profile_id)  # 记录异常
        if job_id is not None:  # 若已有运行记录
            with sched_session_scope() as session:  # 更新状态
                job = session.query(JobRun).filter(JobRun.id == job_id).one()
                job.status = "failed"
                job.finished_at = _now_utc_naive()
                job.error = str(exc)
        emit_metric("error", "profile_failure", 1, profile_id=profile_id)  # 上报失败指标
        inc_run("failed", profile_label)  # 记录失败运行
        observe_latency(profile_label, perf_counter() - start_ts)  # 记录失败耗时
    finally:  # 收尾逻辑
        lock.release()  # 释放锁


def _create_scheduler() -> BackgroundScheduler:  # 创建调度器实例
    """按照配置初始化 APScheduler。"""  # 中文说明

    jobstores = {"default": SQLAlchemyJobStore(url=settings.sched_db_url)}  # 配置 JobStore
    scheduler = BackgroundScheduler(jobstores=jobstores, timezone=settings.tz)  # 创建调度器
    return scheduler  # 返回实例


def _register_jobs(scheduler: BackgroundScheduler) -> None:  # 注册所有 Schedule
    """从数据库读取 schedule 表并注册 cron 任务。"""  # 中文说明

    with sched_session_scope() as session:  # 打开 Session
        schedules = (
            session.query(Schedule)
            .filter(Schedule.is_paused.is_(False))
            .all()
        )  # 查询启用的调度
    for schedule in schedules:  # 遍历记录
        trigger = CronTrigger.from_crontab(schedule.cron_expr, timezone=schedule.tz or settings.tz)  # 构造触发器
        job_id = f"profile-{schedule.profile_id}"  # 构造任务 ID
        scheduler.add_job(
            run_profile,
            trigger=trigger,
            id=job_id,
            args=[schedule.profile_id],
            max_instances=settings.sched_max_parallel,
            coalesce=schedule.coalesce,
            misfire_grace_time=schedule.misfire_grace_sec,
            jitter=schedule.jitter_sec,
            replace_existing=True,
        )  # 注册任务
        LOGGER.info("注册调度 profile_id=%s cron=%s", schedule.profile_id, schedule.cron_expr)  # 记录日志


def start_scheduler() -> BackgroundScheduler:  # 启动函数
    """启动调度服务，返回调度器实例。"""  # 中文说明

    global _SCHEDULER
    if _SCHEDULER is not None:  # 若已存在
        return _SCHEDULER  # 直接返回
    run_migrations()  # 确保调度库迁移
    sync_profiles()  # 同步 Profile
    scheduler = _create_scheduler()  # 创建调度器
    _register_jobs(scheduler)  # 注册任务
    scheduler.start()  # 启动调度器
    _SCHEDULER = scheduler  # 缓存实例
    LOGGER.info("调度服务已启动")  # 记录日志
    return scheduler  # 返回实例


def main() -> None:  # 提供 CLI 入口
    """启动调度服务，保持主线程运行。"""  # 中文说明

    start_scheduler()  # 启动调度
    try:  # 保持运行
        while True:
            threading.Event().wait(60)  # 每分钟阻塞一次
    except KeyboardInterrupt:  # 捕获 Ctrl+C
        if _SCHEDULER:  # 若调度器存在
            _SCHEDULER.shutdown()  # 关闭调度器
        LOGGER.info("调度服务已退出")  # 记录日志


if __name__ == "__main__":  # 支持 python -m 直接运行
    main()  # 调用入口
