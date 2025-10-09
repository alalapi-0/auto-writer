"""平台分发器，串联适配器与 platform_logs 状态机。"""  # 模块中文说明
from __future__ import annotations  # 启用未来注解语法

import json  # 序列化 payload
from datetime import datetime, timedelta, timezone  # 处理时间
from typing import Dict  # 类型提示

from sqlalchemy import text  # 执行原生 SQL
from sqlalchemy.orm import Session  # 引入会话类型

from app.delivery.registry import get_registry  # 加载适配器注册表
from app.delivery.types import DeliveryResult  # 引入统一返回结构


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
        return raw  # 直接返回
    if isinstance(raw, str):  # 若为字符串
        try:
            return datetime.fromisoformat(raw)  # 按 ISO 格式解析
        except ValueError:  # 解析失败
            return None  # 返回空
    return None  # 其他类型不支持


def deliver_article_to_all(db: Session, settings, article_id: int) -> Dict[str, DeliveryResult]:
    """针对单篇文章触发所有启用平台的投递流程。"""  # 函数中文文档

    registry = get_registry(settings)  # 获取平台适配器
    if not registry:  # 若无启用平台
        return {}  # 直接返回空结果
    article_stmt = text("SELECT * FROM articles WHERE id = :id")  # 查询文章 SQL
    article_row = db.execute(article_stmt, {"id": article_id}).mappings().first()  # 执行查询
    if article_row is None:  # 未找到文章
        raise ValueError("article not found")  # 抛出异常
    article = dict(article_row)  # 转换为字典
    results: Dict[str, DeliveryResult] = {}  # 初始化结果
    now = datetime.now(timezone.utc)  # 当前时间
    max_attempts = getattr(settings, "retry_max_attempts", 5)  # 读取最大重试次数
    base_seconds = getattr(settings, "retry_base_seconds", 300)  # 读取基础退避

    for platform, adapter in registry.items():  # 遍历平台
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
            can_run = True  # 可以执行
        else:
            attempts_so_far = int(log.get("attempt_count") or 0)  # 读取历史次数
            status = log.get("status") or "pending"  # 读取状态
            if status in {"success", "prepared", "skipped"}:  # 已完成的状态
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
            res = adapter(article, settings)  # 调用适配器
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
                            payload
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
                            :pl
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
            except Exception:
                trans.rollback()  # 回滚事务
                raise  # 继续抛出异常
            results[platform] = res  # 记录结果
        except Exception as exc:  # 捕获适配器异常
            attempts_now = attempts_so_far + 1  # 累加次数
            wait_seconds = _next_backoff(base_seconds, attempts_now)  # 计算退避
            next_retry = now + timedelta(seconds=wait_seconds)  # 计算下次时间
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
                            payload
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
                            :pl
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
            except Exception:
                trans.rollback()  # 回滚事务
                raise  # 抛出异常
            results[platform] = DeliveryResult(  # 返回失败结果
                platform=platform,
                status="failed",
                target_id=None,
                out_dir=None,
                payload=None,
                error=str(exc),
            )
    return results  # 返回所有平台结果
