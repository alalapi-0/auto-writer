"""Playwright 投递编排器：负责扫描 outbox 与写入 platform_logs。"""  # 模块中文说明
from __future__ import annotations  # 启用未来注解语法

import json  # 序列化 payload
import time  # 统计耗时
from datetime import datetime, timedelta, timezone  # 处理日期与退避
from pathlib import Path  # 操作文件系统
from typing import Dict, Iterable, List, Optional, Tuple  # 类型提示

from sqlalchemy import text  # 执行原生 SQL
from sqlalchemy.orm import Session  # SQLAlchemy 会话类型

from app.delivery.types import DeliveryResult  # 投递结果结构
from app.delivery.wechat_mp_playwright import deliver_via_playwright as deliver_wechat  # 公众号投递
from app.delivery.zhihu_playwright import deliver_via_playwright as deliver_zhihu  # 知乎投递
from app.utils.logger import get_logger  # 日志工具

LOGGER = get_logger(__name__)  # 初始化日志器

PLAYWRIGHT_ADAPTERS = {  # 平台到适配器的映射
    "wechat_mp": deliver_wechat,
    "zhihu": deliver_zhihu,
}

SUCCESS_STATES = {"success", "queued", "prepared"}  # 视为成功的状态集合


def _sanitize_title(title: str) -> str:
    """复制 wechat_adapter 的文件夹命名规则。"""

    cleaned = "".join(ch for ch in title if ch not in "\\/:*?\"<>|").strip()
    return cleaned[:80] or "draft"


def _coerce_datetime(raw) -> Optional[datetime]:
    """将数据库字段转换为 datetime。"""

    if raw is None:
        return None
    if isinstance(raw, datetime):
        return raw if raw.tzinfo else raw.replace(tzinfo=timezone.utc)
    if isinstance(raw, str):
        try:
            parsed = datetime.fromisoformat(raw)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed
        except ValueError:
            return None
    return None


def _load_payload(raw) -> Optional[Dict]:
    """恢复数据库中存储的 JSON payload。"""

    if not raw:
        return None
    if isinstance(raw, dict):
        return raw
    try:
        return json.loads(raw)
    except Exception:  # noqa: BLE001
        return None


def _next_retry(settings, attempt: int) -> Optional[datetime]:
    """根据配置计算下一次重试时间。"""

    base = getattr(settings, "retry_base_seconds", 300)
    if attempt <= 0:
        attempt = 1
    delta = base * (2 ** max(0, attempt - 1))
    return datetime.now(timezone.utc) + timedelta(seconds=delta)


def _find_out_dir(platform: str, title: str, settings, day: Optional[str], preset: Optional[Path]) -> Path:
    """定位草稿目录，支持传入已解析路径。"""

    if preset:
        return preset
    base_dir = Path(getattr(settings, "outbox_dir", "./outbox")) / platform
    day_candidates: Iterable[Path]
    if day:
        day_dir = base_dir / day
        day_candidates = [day_dir]
    else:
        day_candidates = sorted([p for p in base_dir.iterdir() if p.is_dir()], reverse=True)
    safe = _sanitize_title(title)
    for day_dir in day_candidates:
        if not day_dir.exists():
            continue
        candidate = day_dir / safe
        if candidate.exists():
            return candidate
        for child in day_dir.iterdir():
            if not child.is_dir():
                continue
            md_path = child / "draft.md"
            if md_path.exists():
                try:
                    first_line = md_path.read_text(encoding="utf-8").splitlines()[0]
                except Exception:  # noqa: BLE001
                    continue
                first_line = first_line.lstrip("# ").strip()
                if first_line == title:
                    return child
    raise FileNotFoundError(f"未找到草稿目录 platform={platform} title={title}")


def _fetch_article(db: Session, title: str) -> Optional[Dict]:
    """从数据库获取文章记录。"""

    stmt = text("SELECT * FROM articles WHERE title = :title ORDER BY created_at DESC LIMIT 1")
    row = db.execute(stmt, {"title": title}).mappings().first()
    if row:
        return dict(row)
    like_stmt = text("SELECT * FROM articles WHERE title LIKE :like ORDER BY created_at DESC LIMIT 1")
    row = db.execute(like_stmt, {"like": f"%{title}%"}).mappings().first()
    return dict(row) if row else None


def _ensure_platform_log(db: Session, settings, article_id: int, platform: str) -> Tuple[Dict, bool]:
    """确保存在 platform_logs 记录，并根据状态判断是否可以执行。"""

    query = text(
        "SELECT * FROM platform_logs WHERE article_id = :aid AND platform = :pf LIMIT 1"
    )
    row = db.execute(query, {"aid": article_id, "pf": platform}).mappings().first()
    now = datetime.now(timezone.utc)
    max_attempts = getattr(settings, "retry_max_attempts", 5)
    if row:
        attempts = int(row.get("attempt_count") or 0)
        status = row.get("status") or "pending"
        next_retry_at = _coerce_datetime(row.get("next_retry_at"))
        if status == "success":
            return dict(row), False
        if attempts >= max_attempts:
            return dict(row), False
        if next_retry_at and now < next_retry_at:
            return dict(row), False
        update = text(
            "UPDATE platform_logs SET status = :status, next_retry_at = NULL WHERE id = :id"
        )
        db.execute(update, {"status": "queued", "id": row["id"]})
        row = db.execute(query, {"aid": article_id, "pf": platform}).mappings().first()
        return dict(row), True
    insert = text(
        """
        INSERT INTO platform_logs (article_id, platform, status, ok, attempt_count, created_at)
        VALUES (:aid, :pf, 'queued', 0, 0, CURRENT_TIMESTAMP)
        """
    )
    db.execute(insert, {"aid": article_id, "pf": platform})
    row = db.execute(query, {"aid": article_id, "pf": platform}).mappings().first()
    return dict(row), True


def _persist_platform_result(
    db: Session,
    settings,
    log_row: Dict,
    result: DeliveryResult,
) -> None:
    """将 Playwright 调用结果写入 platform_logs。"""

    attempts = int(log_row.get("attempt_count") or 0) + 1
    next_retry_at = None
    error_text = result.error or ""
    if result.status == "failed":
        next_retry_dt = _next_retry(settings, attempts)
        next_retry_at = next_retry_dt.isoformat() if next_retry_dt else None
    payload_json = json.dumps(result.payload or {}, ensure_ascii=False)
    update = text(
        """
        UPDATE platform_logs
        SET target_id = :tid,
            status = :status,
            ok = :ok,
            id_or_url = :idurl,
            error = :error,
            attempt_count = :attempts,
            last_error = :last_error,
            next_retry_at = :next_retry,
            payload = :payload
        WHERE id = :id
        """
    )
    db.execute(
        update,
        {
            "tid": result.target_id,
            "status": result.status,
            "ok": 1 if result.status in SUCCESS_STATES else 0,
            "idurl": result.target_id,
            "error": None if result.status in SUCCESS_STATES else error_text,
            "attempts": attempts,
            "last_error": error_text if result.status == "failed" else None,
            "next_retry": next_retry_at,
            "payload": payload_json,
            "id": log_row["id"],
        },
    )


def _update_run_status(db: Session, run_id: Optional[int], status: str) -> None:
    """根据投递结果更新 runs 状态。"""

    if not run_id:
        return
    stmt = text(
        "UPDATE runs SET status = :status, updated_at = CURRENT_TIMESTAMP WHERE id = :rid"
    )
    db.execute(stmt, {"status": status, "rid": run_id})


def publish_one(
    db: Session,
    settings,
    platform: str,
    title: str,
    day: Optional[str] = None,
    out_dir: Optional[Path] = None,
) -> DeliveryResult:
    """投递单篇草稿，返回适配器执行结果。"""

    adapter = PLAYWRIGHT_ADAPTERS.get(platform)
    if not adapter:
        raise ValueError(f"暂不支持的平台: {platform}")
    article = _fetch_article(db, title)
    if not article:
        raise ValueError(f"数据库中未找到标题为 {title} 的文章")
    out_path = _find_out_dir(platform, title, settings, day, out_dir)
    with db.begin():
        log_row, can_run = _ensure_platform_log(db, settings, article["id"], platform)
        if not can_run:
            payload = _load_payload(log_row.get("payload"))
            return DeliveryResult(
                platform=platform,
                status=log_row.get("status") or "pending",
                target_id=log_row.get("target_id"),
                out_dir=str(out_path),
                payload=payload,
                error=log_row.get("last_error"),
            )
        _update_run_status(db, article.get("run_id"), "delivering")
    start_time = time.time()
    result = adapter({"title": title, "out_dir": str(out_path)}, settings)
    duration = time.time() - start_time
    LOGGER.info(
        "playwright_publish_one",
        platform=platform,
        title=title,
        status=result.status,
        duration=duration,
    )
    with db.begin():
        _persist_platform_result(db, settings, log_row, result)
        if result.status == "success":
            _update_run_status(db, article.get("run_id"), "success")
        elif result.status == "failed":
            _update_run_status(db, article.get("run_id"), "failed")
    return result


def _collect_day_dirs(platform: str, settings, day: Optional[str]) -> List[Path]:
    """收集目标日期的草稿目录列表。"""

    base = Path(getattr(settings, "outbox_dir", "./outbox")) / platform
    if day:
        return [base / day] if (base / day).exists() else []
    today = datetime.now().strftime("%Y%m%d")
    return [base / today] if (base / today).exists() else []


def _detect_title(draft_dir: Path) -> Optional[str]:
    """尽力从 draft.md 推断标题。"""

    md_path = draft_dir / "draft.md"
    if not md_path.exists():
        return None
    try:
        first_line = md_path.read_text(encoding="utf-8").splitlines()[0]
    except Exception:  # noqa: BLE001
        return None
    return first_line.lstrip("# ").strip()


def publish_all(
    db: Session,
    settings,
    day: Optional[str] = None,
    platforms: Optional[List[str]] = None,
) -> Dict[str, object]:
    """批量扫描 outbox 并依次执行 publish_one。"""

    targets = platforms or list(PLAYWRIGHT_ADAPTERS.keys())
    start_time = time.time()
    summary = {
        "success": 0,
        "failed": 0,
        "results": [],
        "screenshots": [],
    }
    for platform in targets:
        for day_dir in _collect_day_dirs(platform, settings, day):
            if not day_dir.exists():
                continue
            for draft_dir in sorted([p for p in day_dir.iterdir() if p.is_dir()]):
                title = _detect_title(draft_dir)
                if not title:
                    LOGGER.warning("publish_all_skip", platform=platform, path=str(draft_dir))
                    continue
                result = publish_one(db, settings, platform, title, day=day_dir.name, out_dir=draft_dir)
                summary["results"].append(result)
                if result.status == "success":
                    summary["success"] += 1
                elif result.status == "failed":
                    summary["failed"] += 1
                    if result.payload and result.payload.get("screenshot"):
                        summary["screenshots"].append(result.payload["screenshot"])
    elapsed = time.time() - start_time
    total = len(summary["results"])
    summary["duration"] = elapsed
    summary["average_duration"] = elapsed / total if total else 0.0
    summary["day"] = day or datetime.now().strftime("%Y%m%d")
    summary["platforms"] = targets
    if total:
        if summary["success"] == total:
            overall = "success"
        elif summary["failed"] == total:
            overall = "failed"
        else:
            overall = "partial"
    else:
        overall = "skipped"
    summary["status"] = overall
    return summary
