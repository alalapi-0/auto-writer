"""封装 APScheduler 调度逻辑，支持定时触发任务。

该模块展示最小可用的每日定时方案，并在注释中说明：
* 如何读取配置中的时区；
* 如何扩展多个时间段与多平台矩阵任务；
* 如何安全关闭调度器避免僵尸线程。
"""

from __future__ import annotations

from datetime import datetime  # 记录调度启动时间
from typing import Optional  # 允许外部覆盖时区

from apscheduler.schedulers.background import (  # 背景调度器，可与主线程并行运行
    BackgroundScheduler,
)
from apscheduler.triggers.cron import CronTrigger  # 使用 cron 表达式描述运行频率
import structlog  # 用于输出结构化调度日志

from config.settings import settings  # 加载全局调度配置（cron + 时区）
from app.main import main  # 调度最终调用主业务流程

LOGGER = structlog.get_logger()  # 初始化结构化日志记录器


def create_scheduler(timezone: Optional[str] = None) -> BackgroundScheduler:
    """创建并返回配置好的调度器实例。

    参数:
        timezone: 可选的时区字符串；若未提供则读取环境变量中的 TIMEZONE。
    """

    scheduler_timezone = timezone or settings.timezone  # 优先使用参数，否则使用配置
    scheduler = BackgroundScheduler(  # 实例化后台调度器
        timezone=scheduler_timezone  # 指定运行时区，使每日固定时间准确触发
    )
    cron_trigger = CronTrigger.from_crontab(  # 创建 cron 触发器
        settings.scheduler.cron_expression  # 读取配置中 cron 表达式，例："0 9 * * *"
    )
    scheduler.add_job(  # 注册每日文章任务
        main,  # 触发时执行 app.main.main 函数
        cron_trigger,
        id="daily_article_job",  # 为任务设定唯一 ID 以便替换/查询
        replace_existing=True,  # 再次启动时覆盖旧任务，避免重复注册
        misfire_grace_time=60 * 5,  # 若错过执行，则允许在 5 分钟内补跑
    )
    # TODO: 后续可在此位置 add_job 多次，形成主题 x 平台的矩阵任务，例如上午英文、下午中文等。
    LOGGER.info(  # 输出调度器创建日志，便于排查配置
        "scheduler_created",
        cron=settings.scheduler.cron_expression,
        timezone=scheduler_timezone,
    )
    return scheduler  # 返回配置好的调度器实例供调用方启动


def start_scheduler() -> None:
    """启动调度器并保持运行，演示最小常驻方案。"""

    scheduler = create_scheduler()  # 创建调度器实例，默认读取配置时区与 cron
    scheduler.start()  # 启动调度器，内部会开启一个后台线程
    LOGGER.info(  # 记录调度启动时间点和任务数量
        "scheduler_started",
        timestamp=datetime.utcnow().isoformat(),
        job_count=len(scheduler.get_jobs()),
    )

    try:
        scheduler.print_jobs()  # 输出当前注册的任务，帮助开发阶段确认配置
        while True:  # 使用无限循环保持主线程存活
            scheduler._thread.join(1)  # 周期性 join 后台线程避免 busy loop
    except (KeyboardInterrupt, SystemExit):  # 捕获终端 Ctrl+C 或系统退出信号
        scheduler.shutdown(wait=False)  # 立即关闭调度器，不等待任务完成
        LOGGER.info("scheduler_stopped")  # 输出停止日志，表明退出流程完成
