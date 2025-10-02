"""封装 APScheduler 调度逻辑，支持定时触发任务。"""

from __future__ import annotations

from datetime import datetime

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
import structlog

from config.settings import settings
from app.main import main

LOGGER = structlog.get_logger()


def create_scheduler() -> BackgroundScheduler:
    """创建并返回配置好的调度器实例。"""

    scheduler = BackgroundScheduler(timezone="Asia/Shanghai")  # 使用上海时区以匹配中文内容发布时间
    cron_trigger = CronTrigger.from_crontab(settings.scheduler.cron_expression)  # 从配置中加载 cron 表达式
    scheduler.add_job(main, cron_trigger, id="daily_article_job", replace_existing=True)  # 注册每日任务
    LOGGER.info("scheduler_created", cron=settings.scheduler.cron_expression)  # 记录调度器创建日志
    return scheduler


def start_scheduler() -> None:
    """启动调度器并保持运行。"""

    scheduler = create_scheduler()  # 创建调度器实例
    scheduler.start()  # 启动调度器开始调度
    LOGGER.info("scheduler_started", timestamp=datetime.utcnow().isoformat())  # 记录调度启动时间

    try:
        scheduler.print_jobs()  # 输出当前任务列表，便于调试
        while True:  # 通过无限循环维持进程常驻
            scheduler._thread.join(1)  # 利用调度器线程的 join 避免 CPU 空转
    except (KeyboardInterrupt, SystemExit):  # 捕获退出信号
        scheduler.shutdown(wait=False)  # 关闭调度器，避免阻塞
        LOGGER.info("scheduler_stopped")  # 输出停止日志
