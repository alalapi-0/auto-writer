"""导出近 N 天运行与指标数据的 JSON 报告。"""  # 模块说明

from __future__ import annotations  # 启用未来注解语法

import argparse  # 解析命令行参数
import json  # 输出 JSON
from datetime import datetime, timedelta, timezone  # 处理时间
from zoneinfo import ZoneInfo  # 处理时区

from app.db.migrate_sched import sched_session_scope, run_migrations  # 调度数据库工具
from app.db.models_sched import JobRun, MetricEvent  # ORM 模型
from config.settings import settings  # 读取全局配置


LOCAL_TZ = ZoneInfo(settings.tz)  # 根据配置构造时区对象


def _local_now() -> datetime:  # 获取配置时区当前时间
    """返回带时区信息的当前时间戳。"""  # 中文说明

    return datetime.now(LOCAL_TZ)  # 使用配置时区获取时间


def _to_utc_naive(value: datetime) -> datetime:  # 转换为朴素 UTC
    """将带时区时间转为 UTC 并移除 tzinfo 以兼容数据库列。"""  # 中文说明

    return value.astimezone(timezone.utc).replace(tzinfo=None)  # 转换到 UTC 并去除时区


def parse_args() -> argparse.Namespace:  # 参数解析
    """解析窗口参数，默认为 7 天。"""  # 中文说明

    parser = argparse.ArgumentParser(description="导出调度运行报告")  # 初始化解析器
    parser.add_argument("--window", type=int, default=7, help="统计天数")  # 时间窗口
    return parser.parse_args()  # 返回参数


def collect_report(window: int) -> dict:  # 收集数据
    """查询 JobRun 与 MetricEvent，组装报告字典。"""  # 中文说明

    now_local = _local_now()  # 获取当前本地时间
    cutoff = _to_utc_naive(now_local - timedelta(days=window))  # 计算截止时间并转换
    with sched_session_scope() as session:  # 打开 Session
        runs = (
            session.query(JobRun)
            .filter(JobRun.started_at >= cutoff)
            .order_by(JobRun.started_at.desc())
            .all()
        )  # 查询 JobRun
        metrics = (
            session.query(MetricEvent)
            .filter(MetricEvent.ts >= cutoff)
            .order_by(MetricEvent.ts.desc())
            .all()
        )  # 查询指标
        run_items = [
            {
                "id": run.id,
                "profile_id": run.profile_id,
                "status": run.status,
                "started_at": run.started_at.isoformat(),
                "finished_at": run.finished_at.isoformat() if run.finished_at else None,
                "emitted": run.emitted_articles,
                "success": run.delivered_success,
                "failed": run.delivered_failed,
            }
            for run in runs
        ]  # 组装运行列表
        metric_items = [
            {
                "id": metric.id,
                "ts": metric.ts.isoformat(),
                "kind": metric.kind,
                "profile_id": metric.profile_id,
                "platform": metric.platform,
                "key": metric.key,
                "value": metric.value,
            }
            for metric in metrics
        ]  # 组装指标列表
    return {"window": window, "generated_at": now_local.isoformat(), "runs": run_items, "metrics": metric_items}  # 返回报告


def main() -> None:  # 主函数
    """解析参数并打印 JSON 报告。"""  # 中文说明

    args = parse_args()  # 解析参数
    run_migrations()  # 确保调度数据库存在
    report = collect_report(args.window)  # 收集报告
    print(json.dumps(report, ensure_ascii=False, indent=2))  # 输出 JSON


if __name__ == "__main__":  # 脚本入口
    main()  # 调用主函数
