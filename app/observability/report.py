# -*- coding: utf-8 -*-  # 指定 UTF-8 编码
"""可观测性报表导出模块，聚合数据库指标并生成 JSON/CSV。"""  # 模块说明

from __future__ import annotations  # 启用未来注解

import csv  # 导出 CSV 文件
import json  # 导出 JSON 文件
from datetime import UTC, datetime, timedelta  # 计算时间窗口并提供时区常量
from pathlib import Path  # 处理文件路径
from typing import Any, Dict, List  # 类型提示

from sqlalchemy import text  # 执行原生 SQL 查询
from sqlalchemy.exc import SQLAlchemyError  # 捕获数据库异常
from sqlalchemy.orm import Session  # 数据库会话类型

from config.settings import settings  # 导入全局配置对象以读取导出目录
from app.db.migrate import SessionLocal  # Session 工厂
from app.utils.logger import get_logger  # 日志模块

LOGGER = get_logger(__name__)  # 初始化模块日志


def _safe_query(session: Session, description: str, sql: str, params: Dict[str, Any], fallback: Any) -> Any:
    """统一执行查询并捕获异常，返回默认值。"""  # 函数说明

    try:  # 捕获数据库异常
        with session.begin():  # 启动事务
            result = session.execute(text(sql), params)  # 执行查询
            data = result.mappings().all()  # 获取结果
            return data  # 返回查询结果
    except SQLAlchemyError as exc:  # 捕获 SQLAlchemy 异常
        LOGGER.error("report_query_failed description=%s error=%s", description, str(exc))  # 记录错误
        return fallback  # 返回默认值


def _collect_article_counts(session: Session, start_iso: str) -> Dict[str, int]:
    """统计每日生成文章数量。"""

    sql = (
        """
        SELECT substr(created_at, 1, 10) AS day, COUNT(*) AS cnt
        FROM articles
        WHERE created_at >= :start
        GROUP BY day
        ORDER BY day ASC
        """
    )  # 构造 SQL
    rows = _safe_query(session, "article_counts", sql, {"start": start_iso}, [])  # 执行查询
    return {row["day"]: row["cnt"] for row in rows}  # 转换为字典


def _collect_dedup_hits(session: Session, start_date: str) -> Dict[str, Any]:
    """统计去重命中情况，优先根据 used_pairs，其次检测标题重复。"""

    result: Dict[str, Any] = {"duplicate_pairs": [], "duplicate_titles": []}  # 初始化结构
    pair_sql = (
        """
        SELECT character_name, work, keyword, COUNT(*) AS cnt
        FROM used_pairs
        WHERE used_on >= :start
        GROUP BY character_name, work, keyword
        HAVING COUNT(*) > 1
        ORDER BY cnt DESC
        LIMIT 10
        """
    )  # 构造 used_pairs 去重命中 SQL
    rows = _safe_query(session, "used_pair_duplicates", pair_sql, {"start": start_date}, [])  # 执行查询
    if rows:  # 若存在重复组合
        result["duplicate_pairs"] = [  # 转换数据结构
            {
                "character_name": row["character_name"],
                "work": row["work"],
                "keyword": row["keyword"],
                "count": row["cnt"],
            }
            for row in rows
        ]
        return result  # 返回结果
    title_sql = (
        """
        SELECT title, COUNT(*) AS cnt
        FROM articles
        WHERE created_at >= :start
        GROUP BY title
        HAVING COUNT(*) > 1
        ORDER BY cnt DESC
        LIMIT 10
        """
    )  # 构造标题重复检测 SQL
    title_rows = _safe_query(session, "article_title_duplicates", title_sql, {"start": start_date + "T00:00:00"}, [])  # 查询
    result["duplicate_titles"] = [  # 转换标题重复数据
        {"title": row["title"], "count": row["cnt"]}
        for row in title_rows
    ]
    return result  # 返回最终结构


def _collect_platform_metrics(session: Session, start_iso: str) -> List[Dict[str, Any]]:
    """统计平台投递成功率与尝试次数。"""

    sql = (
        """
        SELECT platform,
               SUM(CASE WHEN status = 'success' THEN 1 ELSE 0 END) AS success_cnt,
               SUM(CASE WHEN status = 'prepared' THEN 1 ELSE 0 END) AS prepared_cnt,
               SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) AS failed_cnt,
               AVG(attempt_count) AS avg_attempts,
               COUNT(*) AS total_cnt
        FROM platform_logs
        WHERE created_at >= :start
        GROUP BY platform
        """
    )  # 构造统计 SQL
    rows = _safe_query(session, "platform_metrics", sql, {"start": start_iso}, [])  # 执行查询
    metrics: List[Dict[str, Any]] = []  # 初始化列表
    for row in rows:  # 遍历行
        metrics.append(  # 构造指标
            {
                "platform": row["platform"],
                "success": row["success_cnt"] or 0,
                "prepared": row["prepared_cnt"] or 0,
                "failed": row["failed_cnt"] or 0,
                "avg_attempts": float(row["avg_attempts"]) if row["avg_attempts"] is not None else 0.0,
                "total": row["total_cnt"] or 0,
            }
        )
    return metrics  # 返回指标列表


def _collect_top_entities(session: Session, start_iso: str) -> Dict[str, List[Dict[str, Any]]]:
    """统计关键词与角色 TOP10。"""

    result = {"keywords": [], "roles": []}  # 初始化结果
    keyword_sql = (
        """
        SELECT keyword, COUNT(*) AS cnt
        FROM articles
        WHERE created_at >= :start
        GROUP BY keyword
        ORDER BY cnt DESC
        LIMIT 10
        """
    )  # 关键词统计 SQL
    keyword_rows = _safe_query(session, "top_keywords", keyword_sql, {"start": start_iso}, [])  # 执行查询
    result["keywords"] = [  # 转换关键词结果
        {"keyword": row["keyword"], "count": row["cnt"]}
        for row in keyword_rows
    ]
    role_sql = (
        """
        SELECT character_name, COUNT(*) AS cnt
        FROM articles
        WHERE created_at >= :start
        GROUP BY character_name
        ORDER BY cnt DESC
        LIMIT 10
        """
    )  # 角色统计 SQL
    role_rows = _safe_query(session, "top_roles", role_sql, {"start": start_iso}, [])  # 执行查询
    result["roles"] = [  # 转换角色结果
        {"character_name": row["character_name"], "count": row["cnt"]}
        for row in role_rows
    ]
    return result  # 返回结果


def _collect_run_status(session: Session, start_iso: str) -> Dict[str, int]:
    """统计 runs 表状态分布。"""

    sql = (
        """
        SELECT status, COUNT(*) AS cnt
        FROM runs
        WHERE updated_at >= :start
        GROUP BY status
        """
    )  # 构造 SQL
    rows = _safe_query(session, "run_status", sql, {"start": start_iso}, [])  # 执行查询
    return {row["status"]: row["cnt"] for row in rows}  # 转换字典


def generate_report(window_days: int = 7) -> Dict[str, Any]:
    """生成指定窗口的可观测性指标并写入导出文件。"""

    session = SessionLocal()  # 创建数据库会话
    now_utc = datetime.now(UTC)  # 获取当前 UTC 时间
    today = now_utc.date()  # 提取当前日期
    start_date = today - timedelta(days=window_days - 1)  # 计算窗口起始日期
    start_iso = f"{start_date}T00:00:00"  # 转换为 ISO
    LOGGER.info("generate_report_start window_days=%s start=%s", window_days, str(start_date))  # 记录开始
    metrics = {
        "generated_at": now_utc.isoformat(),
        "window": {"start": str(start_date), "end": str(today)},
        "metrics": {},
    }  # 初始化报表结构
    try:  # 捕获报表生成异常
        metrics["metrics"]["article_counts"] = _collect_article_counts(session, start_iso)  # 文章统计
        metrics["metrics"]["dedup_hits"] = _collect_dedup_hits(session, str(start_date))  # 去重命中
        metrics["metrics"]["platform"] = _collect_platform_metrics(session, start_iso)  # 平台指标
        metrics["metrics"]["top_entities"] = _collect_top_entities(session, start_iso)  # 热门关键词与角色
        metrics["metrics"]["run_status"] = _collect_run_status(session, start_iso)  # 运行状态
    finally:
        session.close()  # 关闭会话
    export_dir = Path(settings.exports_dir).expanduser()  # 从配置解析导出目录
    export_dir.mkdir(parents=True, exist_ok=True)  # 确保目录存在
    report_name = f"report_{today.strftime('%Y%m%d')}"  # 生成文件名前缀
    json_path = export_dir / f"{report_name}.json"  # JSON 文件路径
    csv_path = export_dir / f"{report_name}.csv"  # CSV 文件路径
    json_path.write_text(json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8")  # 写入 JSON
    csv_rows = [  # 构造 CSV 行
        {"metric": "generated_at", "value": metrics["generated_at"]},
        {"metric": "window_start", "value": metrics["window"]["start"]},
        {"metric": "window_end", "value": metrics["window"]["end"]},
        {"metric": "article_counts", "value": json.dumps(metrics["metrics"]["article_counts"], ensure_ascii=False)},
        {"metric": "dedup_hits", "value": json.dumps(metrics["metrics"]["dedup_hits"], ensure_ascii=False)},
        {"metric": "platform", "value": json.dumps(metrics["metrics"]["platform"], ensure_ascii=False)},
        {"metric": "top_entities", "value": json.dumps(metrics["metrics"]["top_entities"], ensure_ascii=False)},
        {"metric": "run_status", "value": json.dumps(metrics["metrics"]["run_status"], ensure_ascii=False)},
    ]
    with csv_path.open("w", encoding="utf-8", newline="") as fh:  # 打开 CSV 文件
        writer = csv.DictWriter(fh, fieldnames=["metric", "value"])  # 创建写入器
        writer.writeheader()  # 写入表头
        writer.writerows(csv_rows)  # 写入数据
    LOGGER.info("generate_report_finish json=%s csv=%s", str(json_path), str(csv_path))  # 记录完成
    return {"json": json_path, "csv": csv_path, "data": metrics}  # 返回结果
