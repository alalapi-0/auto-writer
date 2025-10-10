"""平台分发器，串联适配器与 platform_logs 状态机。"""  # 模块中文说明
from __future__ import annotations  # 启用未来注解语法

import json  # 序列化 payload
from datetime import datetime, timedelta, timezone  # 处理时间
from typing import Dict  # 类型提示

from sqlalchemy import text  # 执行原生 SQL
from sqlalchemy.orm import Session  # 引入会话类型
from tenacity import RetryError, retry, stop_after_attempt, wait_random_exponential  # 引入重试工具

from app.utils.logger import get_logger  # 引入统一日志模块

from app.delivery.registry import get_registry  # 加载适配器注册表
from app.delivery.types import DeliveryResult  # 引入统一返回结构
from app.plugins.loader import run_exporter_hook  # 引入插件导出 Hook
from app.telemetry.client import emit_metric  # 指标事件
from app.telemetry.metrics import inc_delivery  # Prometheus 计数


def _next_backoff(base_seconds: int, attempt: int) -> int:
    """根据指数退避计算下一次等待秒数。"""  # 函数中文文档

    return base_seconds * (2 ** max(0, attempt - 1))  # 退避因子


def _load_payload(raw) -> Dict | None:
    """尝试将数据库中的 payload 转换为字典。"""  # 辅助函数中文说明

    if raw in (None, "", b""):  # 空值直接返回
        return None  # 返回空
    if isinstance(raw, (dict, list)):  # 已经是结构
        return raw  # 直接返回
    try:  # 尝试解析 JSON
        return json.loads(raw)  # 解析字符串
    except Exception:  # noqa: BLE001  # 解析失败忽略
        return None  # 返回空


def _coerce_datetime(raw):
    """将数据库返回的时间值转换为 datetime 对象。"""  # 辅助函数中文说明

    if raw is None:  # 空值直接返回
        return None  # 返回 None
    if isinstance(raw, datetime):  # 已是 datetime
        return raw if raw.tzinfo else raw.replace(tzinfo=timezone.utc)  # 保证带时区
    if isinstance(raw, str):  # 若为字符串
        try:
            parsed = datetime.fromisoformat(raw)  # 按 ISO 格式解析
            if parsed.tzinfo is None:  # 若解析结果无时区
                parsed = parsed.replace(tzinfo=timezone.utc)  # 补充 UTC 时区
            return parsed  # 返回规范化时间
        except ValueError:  # 解析失败
            return None  # 返回空
    return None  # 其他类型不支持


def _call_adapter_with_retry(adapter, article: Dict, settings) -> DeliveryResult:
    """封装外部适配器调用，统一应用退避重试策略。"""  # 中文说明

    @retry(  # 使用 tenacity 装饰器
        stop=stop_after_attempt(settings.job_max_retries),  # 最大尝试次数
        wait=wait_random_exponential(
            multiplier=settings.job_retry_backoff_sec, max=settings.job_retry_backoff_sec * 10
        ),  # 指数退避加抖动
        reraise=True,  # 重试耗尽抛出异常
    )
    def _invoke() -> DeliveryResult:  # 内部执行函数
        return adapter(article, settings)  # 实际调用适配器

    return _invoke()  # 返回结果


def _find_duplicate_log(db: Session, article: Dict, platform: str) -> Dict | None:
    """根据标题与角色组合检测重复投递。"""  # 中文说明

    title = article.get("title")  # 标题
    character = article.get("character_name")  # 角色
    work = article.get("work")  # 作品
    created_at = _coerce_datetime(article.get("created_at"))  # 创建时间
    if not all([title, character, work, created_at]):  # 字段缺失时直接跳过
        return None
    stmt = text(
        """
        SELECT pl.*
        FROM platform_logs pl
        JOIN articles a ON pl.article_id = a.id
        WHERE pl.platform = :platform
          AND a.title = :title
          AND a.character_name = :character
          AND a.work = :work
          AND DATE(pl.created_at) = :day
        LIMIT 1
        """
    )  # SQL 语句
    row = db.execute(
        stmt,
        {
            "platform": platform,
            "title": title,
            "character": character,
            "work": work,
            "day": created_at.date().isoformat(),
        },
    ).mappings().first()  # 执行查询
    return dict(row) if row else None  # 返回字典或 None


def deliver_article_to_all(db: Session, settings, article_id: int) -> Dict[str, DeliveryResult]:
    """针对单篇文章触发所有启用平台的投递流程。"""  # 函数中文文档

    registry = get_registry(settings)  # 获取平台适配器
    LOGGER.info("准备投递文章 article_id=%s platforms=%s", article_id, list(registry.keys()))  # 记录投递任务启动
    if not registry:  # 若无启用平台
        LOGGER.warning("未启用投递平台 article_id=%s", article_id)  # 记录提示信息
        return {}  # 直接返回空结果
    article_stmt = text("SELECT * FROM articles WHERE id = :id")  # 查询文章 SQL
    article_row = db.execute(article_stmt, {"id": article_id}).mappings().first()  # 执行查询
    if article_row is None:  # 未找到文章
        LOGGER.error("文章不存在，无法投递 article_id=%s", article_id)  # 输出错误日志
        raise ValueError("article not found")  # 抛出异常
    article = dict(article_row)  # 转换为字典
    results: Dict[str, DeliveryResult] = {}  # 初始化结果
    now = datetime.now(timezone.utc)  # 当前时间
    max_attempts = getattr(settings, "retry_max_attempts", 5)  # 读取最大重试次数
    base_seconds = getattr(settings, "retry_base_seconds", 300)  # 读取基础退避

    for platform, adapter in registry.items():  # 遍历平台
        duplicate_log = _find_duplicate_log(db, article, platform)  # 检查重复记录
        if duplicate_log:  # 命中重复则直接跳过
            LOGGER.info(
                "delivery_duplicate_skip",
                platform=platform,
                article_id=article_id,
                log_id=duplicate_log.get("id"),
            )
            emit_metric("delivery", "duplicate_skip", 1, platform=platform)  # 记录重复指标
            payload = _load_payload(duplicate_log.get("payload"))  # 恢复历史 payload
            results[platform] = DeliveryResult(  # 返回历史结果
                platform=platform,
                status=duplicate_log.get("status") or "skipped",
                target_id=duplicate_log.get("target_id"),
                out_dir=None,
                payload=payload,
                error=duplicate_log.get("last_error"),
            )
            inc_delivery(platform, duplicate_log.get("status") or "skipped")  # 记录 Prometheus
            continue
        log_stmt = text(
            """
            SELECT *
            FROM platform_logs
            WHERE article_id = :aid AND platform = :pf
            LIMIT 1
            """
        )  # 查询日志语句
        log = db.execute(log_stmt, {"aid": article_id, "pf": platform}).mappings().first()  # 执行查询
        can_run = False  # 默认不可执行
        attempts_so_far = 0  # 当前尝试次数
        if log is None:  # 首次投递
            LOGGER.info("首次平台投递 platform=%s article_id=%s", platform, article_id)  # 记录首次投递
            can_run = True  # 可以执行
        else:
            attempts_so_far = int(log.get("attempt_count") or 0)  # 读取历史次数
            status = log.get("status") or "pending"  # 读取状态
            if status in {"success", "prepared", "skipped"}:  # 已完成的状态
                LOGGER.info(  # 已完成的平台直接跳过
                    "平台已完成 platform=%s article_id=%s status=%s",
                    platform,
                    article_id,
                    status,
                )
                results[platform] = DeliveryResult(  # 构造返回
                    platform=platform,
                    status=status,  # 原始状态
                    target_id=log.get("target_id"),  # 历史 ID
                    out_dir=None,
                    payload=_load_payload(log.get("payload")),  # 恢复 payload
                    error=log.get("last_error"),  # 历史错误
                )
                continue  # 跳过
            if attempts_so_far >= max_attempts:  # 超过重试上限
                LOGGER.warning(  # 记录超过重试上限的情况
                    "达到重试上限 article_id=%s platform=%s attempts=%s",
                    article_id,
                    platform,
                    attempts_so_far,
                )
                results[platform] = DeliveryResult(  # 返回失败状态
                    platform=platform,
                    status=status,
                    target_id=log.get("target_id"),
                    out_dir=None,
                    payload=_load_payload(log.get("payload")),
                    error=log.get("last_error"),
                )
                continue  # 不再执行
            next_retry_at = _coerce_datetime(log.get("next_retry_at"))  # 读取并转换预约时间
            if next_retry_at is None or now >= next_retry_at:  # 判断是否到期
                can_run = True  # 可以执行
        if not can_run:  # 未到执行窗口
            LOGGER.info(  # 记录等待重试的情况
                "等待下一次重试 article_id=%s platform=%s next_retry_at=%s",
                article_id,
                platform,
                log.get("next_retry_at") if log else None,
            )
            results[platform] = DeliveryResult(  # 返回原状态
                platform=platform,
                status=log.get("status") if log else "pending",
                target_id=log.get("target_id") if log else None,
                out_dir=None,
                payload=_load_payload(log.get("payload")) if log else None,
                error=log.get("last_error") if log else None,
            )
            continue  # 处理下个平台
        try:
            LOGGER.info(  # 记录本次平台投递开始
                "执行平台投递 article_id=%s platform=%s attempt=%s",
                article_id,
                platform,
                attempts_so_far + 1,
            )
            run_exporter_hook("on_before_publish", article, platform)  # 投递前触发插件 Hook
            try:
                res = _call_adapter_with_retry(adapter, article, settings)  # 调用适配器并自动重试
            except RetryError as exc:  # 捕获重试耗尽
                last_exc = exc.last_attempt.exception() if exc.last_attempt else exc  # 获取最终异常
                LOGGER.error(
                    "delivery_adapter_failed",
                    platform=platform,
                    article_id=article_id,
                    error=str(last_exc),
                )
                res = DeliveryResult(  # 构造失败结果
                    platform=platform,
                    status="failed",
                    target_id=None,
                    out_dir=None,
                    payload={"retry_attempts": exc.last_attempt.attempt_number if exc.last_attempt else settings.job_max_retries},
                    error=str(last_exc),
                )
            payload_json = json.dumps(res.payload or {}, ensure_ascii=False)  # 序列化 payload
            ok_flag = res.status in {"prepared", "queued", "success"}  # 判断成功
            trans = db.begin_nested() if db.in_transaction() else db.begin()  # 兼容已有事务的开启方式
            try:
                if log is None:  # 首次写入
                    insert_stmt = text(
                        """
                        INSERT INTO platform_logs (
                            article_id,
                            platform,
                            target_id,
                            status,
                            ok,
                            id_or_url,
                            error,
                            attempt_count,
                            last_error,
                            next_retry_at,
                            payload,
                            created_at
                        )
                        VALUES (
                            :aid,
                            :pf,
                            :tid,
                            :st,
                            :ok,
                            :id_url,
                            :err,
                            :ac,
                            :last_err,
                            :nra,
                            :pl,
                            :created_at
                        )
                        """
                    )  # 插入语句
                    db.execute(
                        insert_stmt,
                        {
                            "aid": article_id,
                            "pf": platform,
                            "tid": res.target_id,
                            "st": res.status,
                            "ok": ok_flag,
                            "id_url": res.target_id,
                            "err": res.error,
                            "ac": attempts_so_far + 1,
                            "last_err": res.error,
                            "nra": None,
                            "pl": payload_json,
                            "created_at": now.isoformat(),
                        },
                    )  # 执行插入
                else:
                    update_stmt = text(
                        """
                        UPDATE platform_logs
                        SET target_id = :tid,
                            status = :st,
                            ok = :ok,
                            id_or_url = :id_url,
                            error = :err,
                            attempt_count = :ac,
                            last_error = :last_err,
                            next_retry_at = :nra,
                            payload = :pl
                        WHERE id = :id
                        """
                    )  # 更新语句
                    next_retry = None  # 默认不安排重试
                    if res.status == "failed":  # 失败时计算下一次重试时间
                        wait_seconds = _next_backoff(base_seconds, attempts_so_far + 1)
                        next_retry = now + timedelta(seconds=wait_seconds)
                    db.execute(
                        update_stmt,
                        {
                            "id": log.get("id"),
                            "tid": res.target_id,
                            "st": res.status,
                            "ok": ok_flag,
                            "id_url": res.target_id,
                            "err": res.error,
                            "ac": attempts_so_far + 1,
                            "last_err": res.error,
                            "nra": next_retry,
                            "pl": payload_json,
                        },
                    )  # 执行更新
                trans.commit()  # 提交事务
                LOGGER.info(  # 记录事务提交成功
                    "平台投递写入成功 article_id=%s platform=%s status=%s",
                    article_id,
                    platform,
                    res.status,
                )
                if res.status in {"prepared", "queued", "success"}:  # 成功状态
                    emit_metric("delivery", "platform_success", 1, platform=platform)  # 记录成功指标
                else:
                    emit_metric("delivery", "platform_failed", 1, platform=platform)  # 记录失败指标
                inc_delivery(platform, res.status)  # 同步 Prometheus 计数
            except Exception:
                trans.rollback()  # 回滚事务
                LOGGER.exception(  # 记录回滚原因
                    "平台投递写入失败 article_id=%s platform=%s",
                    article_id,
                    platform,
                )
                raise  # 继续抛出异常
            run_exporter_hook(
                "on_after_publish",
                {"article_id": article_id, "status": res.status, "target": res.target_id},
                platform,
            )  # 投递完成后触发插件 Hook
            results[platform] = res  # 记录结果
        except Exception as exc:  # 捕获适配器异常
            attempts_now = attempts_so_far + 1  # 累加次数
            wait_seconds = _next_backoff(base_seconds, attempts_now)  # 计算退避
            next_retry = now + timedelta(seconds=wait_seconds)  # 计算下次时间
            LOGGER.error(  # 记录投递失败信息
                "平台投递异常 article_id=%s platform=%s attempts=%s error=%s",
                article_id,
                platform,
                attempts_now,
                str(exc),
            )
            trans = db.begin_nested() if db.in_transaction() else db.begin()  # 兼容已有事务的开启方式
            try:
                if log is None:
                    fail_insert = text(
                        """
                        INSERT INTO platform_logs (
                            article_id,
                            platform,
                            target_id,
                            status,
                            ok,
                            id_or_url,
                            error,
                            attempt_count,
                            last_error,
                            next_retry_at,
                            payload,
                            created_at
                        )
                        VALUES (
                            :aid,
                            :pf,
                            NULL,
                            'failed',
                            0,
                            NULL,
                            :err,
                            :ac,
                            :err,
                            :nra,
                            :pl,
                            :created_at
                        )
                        """
                    )  # 失败插入
                    db.execute(
                        fail_insert,
                        {
                            "aid": article_id,
                            "pf": platform,
                            "err": str(exc),
                            "ac": attempts_now,
                            "nra": next_retry,
                            "pl": json.dumps({}, ensure_ascii=False),
                            "created_at": now.isoformat(),
                        },
                    )  # 执行插入
                else:
                    fail_update = text(
                        """
                        UPDATE platform_logs
                        SET status = 'failed',
                            ok = 0,
                            error = :err,
                            attempt_count = :ac,
                            last_error = :err,
                            next_retry_at = :nra
                        WHERE id = :id
                        """
                    )  # 失败更新
                    db.execute(
                        fail_update,
                        {
                            "id": log.get("id"),
                            "err": str(exc),
                            "ac": attempts_now,
                            "nra": next_retry,
                        },
                    )  # 执行更新
                trans.commit()  # 提交失败写入
                LOGGER.info(  # 记录失败信息已落库
                    "平台失败信息已记录 article_id=%s platform=%s next_retry_at=%s",
                    article_id,
                    platform,
                    next_retry.isoformat(),
                )
            except Exception:
                trans.rollback()  # 回滚事务
                LOGGER.exception(  # 记录失败记录写入异常
                    "平台失败写入失败 article_id=%s platform=%s",
                    article_id,
                    platform,
                )
                raise  # 抛出异常
            results[platform] = DeliveryResult(  # 返回失败结果
                platform=platform,
                status="failed",
                target_id=None,
                out_dir=None,
                payload=None,
                error=str(exc),
            )
    LOGGER.info("文章投递流程结束 article_id=%s", article_id)  # 记录整体结束
    return results  # 返回所有平台结果

LOGGER = get_logger(__name__)  # 获取模块专用记录器
