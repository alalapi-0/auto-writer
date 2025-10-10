"""Dashboard FastAPI 服务，提供页面与 API。"""  # 模块说明

from __future__ import annotations  # 启用未来注解语法

import csv  # 导出 CSV
from contextlib import contextmanager  # 提供主库 Session 上下文
from datetime import datetime  # 审核动作时间戳
from difflib import SequenceMatcher  # 估算文本编辑幅度
from io import StringIO  # 构建内存 CSV
from pathlib import Path  # 处理路径
from typing import Any, Dict, List, Optional  # 类型提示

from fastapi import Depends, FastAPI, HTTPException, Request, Response, status  # FastAPI 核心组件
from fastapi.responses import HTMLResponse, JSONResponse  # 响应类型
from fastapi.staticfiles import StaticFiles  # 静态文件支持
from fastapi.templating import Jinja2Templates  # 模板渲染

from config.settings import settings  # 引入配置
from app.auth.security import (  # 鉴权工具
    create_access_token,
    get_current_user,
    verify_password,
)
from app.auth.oidc import router as oidc_router  # 引入 OIDC 路由
from app.db.migrate import SessionLocal as MainSessionLocal  # 主业务库会话工厂
from app.db.migrate_sched import run_migrations, sched_session_scope  # 调度数据库工具
from app.db import models  # 主业务库 ORM 模型
from app.db.models_sched import JobRun, MetricEvent, Schedule, User  # ORM 模型
from app.dispatch.api import router as dispatch_router  # 分发队列路由
from app.dispatch.store import run_dispatch_migrations  # 分发库迁移
from app.dashboard.views.alerts import router as alerts_router  # 告警面板路由
from app.scheduler.api import list_schedules, pause_schedule, resume_schedule, run_now  # 调度控制
from app.utils.logger import get_logger  # 日志工具
from app.telemetry.metrics import (  # Prometheus 指标工具
    PROMETHEUS_ENABLED,  # 指标开关
    generate_latest_metrics,  # 序列化指标函数
)  # 导入结束
from app.prompting import feedback as prompt_feedback  # 引入反馈模块
from app.delivery.dispatcher import deliver_article_to_all  # 审核后触发投递

LOGGER = get_logger(__name__)  # 初始化日志

app = FastAPI(title="AutoWriter Dashboard")  # 创建 FastAPI 应用

TEMPLATES = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))  # 模板目录
app.mount("/static", StaticFiles(directory=str(Path(__file__).parent / "static")), name="static")  # 挂载静态目录
app.include_router(oidc_router)  # 注册 OIDC 相关路由
app.include_router(dispatch_router)  # 注册分发队列路由
app.include_router(alerts_router)  # 注册告警面板路由


@contextmanager
def main_session_scope():  # 主库 Session 上下文管理器
    """提供与业务数据库交互的上下文，确保连接正确释放。"""

    session = MainSessionLocal()
    try:
        yield session  # 向调用方暴露 Session
    finally:
        session.close()  # 确保连接被关闭


def _review_field_to_attr(field: str) -> str:  # 将复核字段映射到 ORM 属性
    mapping = {
        "body": "content",  # body 对应 content 字段
    }
    return mapping.get(field, field)  # 默认返回原字段


def _normalize_patch_value(field: str, value: Any) -> Any:  # 规范化复核输入
    if field == "tags":  # 标签允许字符串或列表
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        if isinstance(value, (list, tuple)):
            return [str(item).strip() for item in value if str(item).strip()]
        return None
    if field in {"title", "summary", "body"}:  # 文本字段强制转字符串
        return None if value is None else str(value)
    return value


def _value_to_text(value: Any) -> str:  # 将任意值转为比较所需的文本
    if value is None:
        return ""
    if isinstance(value, (list, tuple)):
        return ",".join(str(item) for item in value)
    return str(value)


def _calculate_edit_impact(before: Any, after: Any) -> tuple[int, float]:  # 估算编辑规模
    before_text = _value_to_text(before)
    after_text = _value_to_text(after)
    if before_text == after_text:
        return 0, 0.0
    matcher = SequenceMatcher(None, before_text, after_text)
    similarity = matcher.ratio()
    ratio = max(0.0, min(1.0, 1.0 - similarity))
    baseline = max(len(before_text), len(after_text), 1)
    delta = int(round(baseline * ratio))
    return delta, ratio


def _extract_edit_ratio(diffs: Optional[dict]) -> float:  # 从 diff 聚合中提取总体幅度
    if not isinstance(diffs, dict):
        return 0.0
    metrics = diffs.get("metrics") or {}
    total_before = float(metrics.get("total_before") or 0.0)
    total_delta = float(metrics.get("total_char_delta") or 0.0)
    if total_before <= 0:
        return 0.0
    return max(0.0, min(1.0, total_delta / total_before))


if PROMETHEUS_ENABLED:  # 当启用 Prometheus 时注册指标路由

    @app.get("/metrics")  # 暴露指标的 HTTP 路由
    def metrics_endpoint() -> Response:  # 指标路由处理函数
        """返回 Prometheus 指标内容。"""  # 中文说明

        body, content_type = generate_latest_metrics()  # 获取指标字节串与类型
        return Response(content=body, media_type=content_type)  # 构造响应


@app.on_event("startup")  # 注册启动事件
async def on_startup() -> None:  # 启动事件
    """确保调度数据库存在并同步 Profile。"""  # 中文说明

    run_migrations()  # 执行迁移
    run_dispatch_migrations()  # 确保分发数据库建表


@app.get("/healthz")  # 健康检查路由
def healthz() -> dict[str, str]:  # 健康检查
    """返回简单的健康状态。"""  # 中文说明

    return {"status": "ok"}  # 健康状态


def _collect_prompt_experiment_stats(session: Any) -> Dict[str, Any]:  # 统计 Prompt 实验数据
    """聚合 ContentAudit 表中各 Variant 的表现。"""  # 中文说明

    audits: List[models.ContentAudit] = session.query(models.ContentAudit).all()  # 查询全部审计记录
    total = len(audits)  # 计算总量
    buckets: Dict[str, Dict[str, Any]] = {}  # 初始化聚合桶
    for audit in audits:  # 遍历记录
        variant = audit.prompt_variant or "unknown"  # 缺省命名为 unknown
        bucket = buckets.setdefault(variant, {"count": 0, "scores": [], "fallback": 0})  # 获取桶
        bucket["count"] += 1  # 累计次数
        overall = None
        if isinstance(audit.scores, dict):  # 安全读取 overall 分数
            overall = audit.scores.get("overall")
        if isinstance(overall, (int, float)):  # 仅记录数值型分数
            bucket["scores"].append(float(overall))
        bucket["fallback"] += audit.fallback_count  # 累加失败切换次数
    summary: List[Dict[str, Any]] = []  # 汇总结果
    for variant, info in buckets.items():  # 遍历聚合结果
        count = info["count"]
        hit_rate = count / total if total else 0.0  # 计算命中率
        avg_score = sum(info["scores"]) / len(info["scores"]) if info["scores"] else 0.0  # 平均质量分
        avg_fallback = info["fallback"] / count if count else 0.0  # 平均失败切换次数
        summary.append(
            {
                "variant": variant,
                "count": count,
                "hit_rate": hit_rate,
                "avg_quality": avg_score,
                "avg_fallback": avg_fallback,
            }
        )  # 记录摘要
    summary.sort(key=lambda item: item["count"], reverse=True)  # 按使用次数排序
    return {"total": total, "items": summary}  # 返回聚合数据


@app.get("/review/queue")
def api_review_queue(
    queue_status: str = "pending",
    limit: int = 20,
    offset: int = 0,
    user=Depends(get_current_user("operator")),
) -> Dict[str, Any]:  # 列出人工复核队列
    """返回人工复核队列列表，支持分页。"""

    if limit <= 0 or limit > 200:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid limit")
    if offset < 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid offset")
    with main_session_scope() as session:
        query = session.query(models.ReviewQueue)
        if queue_status:
            query = query.filter(models.ReviewQueue.status == queue_status)
        total = query.count()
        rows = (
            query.order_by(models.ReviewQueue.created_at.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )
        items: List[Dict[str, Any]] = []
        for row in rows:
            article = row.article
            audit = article.quality_audit if article else None
            items.append(
                {
                    "id": row.id,
                    "draft_id": row.draft_id,
                    "title": article.title if article else None,
                    "keyword": article.keyword if article else None,
                    "status": row.status,
                    "reason": row.reason,
                    "created_at": row.created_at.isoformat() if row.created_at else None,
                    "reviewer": row.reviewer,
                    "reviewed_at": row.reviewed_at.isoformat() if row.reviewed_at else None,
                    "prompt_variant": audit.prompt_variant if audit else None,
                    "quality": (audit.scores or {}).get("overall") if audit and isinstance(audit.scores, dict) else None,
                }
            )
    return {"total": total, "items": items, "limit": limit, "offset": offset}


@app.get("/review/{review_id}")
def api_review_detail(
    review_id: int, user=Depends(get_current_user("operator"))
) -> Dict[str, Any]:  # 返回单条复核详情
    """展示人工复核详情，包括质量分与差异记录。"""

    with main_session_scope() as session:
        row = (
            session.query(models.ReviewQueue)
            .filter(models.ReviewQueue.id == review_id)
            .one_or_none()
        )
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="review not found")
        article = row.article
        audit = article.quality_audit if article else None
        detail = {
            "id": row.id,
            "status": row.status,
            "reason": row.reason,
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "reviewer": row.reviewer,
            "reviewed_at": row.reviewed_at.isoformat() if row.reviewed_at else None,
            "diffs": row.diffs_json,
            "article": {
                "id": article.id if article else None,
                "title": article.title if article else None,
                "summary": article.summary if article else None,
                "tags": article.tags if article else None,
                "content": article.content if article else None,
                "keyword": article.keyword if article else None,
                "status": article.status if article else None,
            },
            "quality": {
                "scores": audit.scores if audit else None,
                "reasons": audit.reasons if audit else None,
                "attempts": audit.attempts if audit else None,
                "prompt_variant": audit.prompt_variant if audit else None,
                "passed": audit.passed if audit else False,
            },
        }
    return detail


@app.post("/review/{review_id}/patch")
def api_review_patch(
    review_id: int,
    payload: Dict[str, Any],
    user=Depends(get_current_user("operator")),
) -> Dict[str, Any]:  # 编辑草稿允许的字段
    """允许在人工复核过程中对指定字段做小幅编辑。"""

    allowed = set(settings.qa_edit_allow_fields)
    requested = {key: payload[key] for key in payload.keys() & allowed}
    if not requested:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="no editable fields provided")

    with main_session_scope() as session:
        row = (
            session.query(models.ReviewQueue)
            .filter(models.ReviewQueue.id == review_id)
            .one_or_none()
        )
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="review not found")
        if row.status != "pending":
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="review already closed")
        article = row.article
        if article is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="article not found")

        diffs = dict(row.diffs_json or {})
        edits: List[Dict[str, Any]] = list(diffs.get("edits") or [])
        metrics = dict(diffs.get("metrics") or {"total_char_delta": 0, "total_before": 0})
        changed_entries: List[Dict[str, Any]] = []

        for field, value in requested.items():
            attr = _review_field_to_attr(field)
            normalized = _normalize_patch_value(field, value)
            before_value = getattr(article, attr)
            if normalized == before_value:
                continue
            setattr(article, attr, normalized)
            delta, ratio = _calculate_edit_impact(before_value, normalized)
            baseline = max(len(_value_to_text(before_value)), 1)
            metrics["total_char_delta"] = metrics.get("total_char_delta", 0) + delta
            metrics["total_before"] = metrics.get("total_before", 0) + baseline
            edit_entry = {
                "field": field,
                "before": before_value,
                "after": normalized,
                "char_delta": delta,
                "ratio": ratio,
                "reviewer": user.username,
                "edited_at": datetime.utcnow().isoformat() + "Z",
            }
            edits.append(edit_entry)
            changed_entries.append(edit_entry)

        if not changed_entries:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="nothing changed")

        diffs["edits"] = edits
        diffs["metrics"] = metrics
        diffs["last_editor"] = user.username
        diffs["updated_at"] = datetime.utcnow().isoformat() + "Z"
        row.diffs_json = diffs
        session.commit()

    return {"status": "patched", "edits": changed_entries, "diffs": diffs}


@app.post("/review/{review_id}/approve")
def api_review_approve(
    review_id: int,
    payload: Optional[Dict[str, Any]] = None,
    user=Depends(get_current_user("operator")),
) -> Dict[str, Any]:  # 审核通过
    """将复核记录标记为通过，并根据配置触发投递。"""

    auto_deliver = settings.qa_approve_autodeliver
    now = datetime.utcnow()
    variant: Optional[str] = None
    edit_ratio = 0.0
    total_delta = 0.0
    with main_session_scope() as session:
        row = (
            session.query(models.ReviewQueue)
            .filter(models.ReviewQueue.id == review_id)
            .one_or_none()
        )
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="review not found")
        if row.status != "pending":
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="review already closed")
        article = row.article
        if article is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="article not found")
        audit = article.quality_audit
        if audit:
            variant = audit.prompt_variant
        diffs = dict(row.diffs_json or {})
        metrics = diffs.get("metrics") or {}
        total_delta = float(metrics.get("total_char_delta") or 0.0)
        edit_ratio = _extract_edit_ratio(diffs)

        row.status = "approved"
        row.reviewer = user.username
        row.reviewed_at = now
        article.status = "approved"
        diffs.setdefault("decision", {})
        diffs["decision"].update(
            {
                "status": "approved",
                "reviewer": user.username,
                "reviewed_at": now.isoformat() + "Z",
                "auto_deliver": auto_deliver,
            }
        )
        row.diffs_json = diffs

        if audit:
            audit.manual_review = False
            audit.human_feedback = "approved"
            audit.edit_impact = edit_ratio

        delivery_result: Optional[Dict[str, Any]] = None
        if auto_deliver:
            try:
                results = deliver_article_to_all(session, settings, article_id=article.id)
                delivery_result = {platform: res.status for platform, res in results.items()}
                diffs["decision"]["delivery_status"] = delivery_result
            except Exception as exc:  # noqa: BLE001
                diffs["decision"]["delivery_error"] = str(exc)
                LOGGER.exception("auto delivery failed article_id=%s", article.id)

        session.commit()

    outcome = "approve_minor"
    if edit_ratio > 0.15 or total_delta > 150:
        outcome = "approve_major"
    prompt_feedback.record_review_outcome(variant, outcome, edit_ratio)
    return {
        "status": "approved",
        "auto_deliver": auto_deliver,
        "edit_ratio": edit_ratio,
        "delivery": delivery_result,
    }


@app.post("/review/{review_id}/reject")
def api_review_reject(
    review_id: int,
    payload: Optional[Dict[str, Any]] = None,
    user=Depends(get_current_user("operator")),
) -> Dict[str, Any]:  # 审核驳回
    """将复核记录标记为驳回，同时回写 Prompt 实验统计。"""

    reason = (payload or {}).get("reason", "质量不达标")
    now = datetime.utcnow()
    variant: Optional[str] = None
    with main_session_scope() as session:
        row = (
            session.query(models.ReviewQueue)
            .filter(models.ReviewQueue.id == review_id)
            .one_or_none()
        )
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="review not found")
        if row.status != "pending":
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="review already closed")
        article = row.article
        if article is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="article not found")
        audit = article.quality_audit
        if audit:
            variant = audit.prompt_variant
            audit.manual_review = False
            audit.human_feedback = "rejected"
            audit.edit_impact = 1.0
        row.status = "rejected"
        row.reviewer = user.username
        row.reviewed_at = now
        article.status = "rejected"
        diffs = dict(row.diffs_json or {})
        diffs.setdefault("decision", {})
        diffs["decision"].update(
            {
                "status": "rejected",
                "reviewer": user.username,
                "reviewed_at": now.isoformat() + "Z",
                "reason": reason,
            }
        )
        row.diffs_json = diffs
        session.commit()

    prompt_feedback.record_review_outcome(variant, "rejected", 1.0)
    return {"status": "rejected", "reason": reason}


@app.post("/api/login")  # 登录 API 路由
def api_login(payload: dict[str, Any]) -> dict[str, str]:  # 登录接口
    """校验用户名密码并返回 JWT。"""  # 中文说明

    username = payload.get("username", "")  # 读取用户名
    password = payload.get("password", "")  # 读取密码
    with sched_session_scope() as session:  # 打开 Session
        user = session.query(User).filter(User.username == username).one_or_none()  # 查询用户
        if user is None or not verify_password(password, user.password_hash):  # 校验失败
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")  # 抛出异常
        token = create_access_token(subject=user.username, role=user.role)  # 签发 token
        return {"access_token": token}  # 返回 token


@app.get("/api/runs")  # 运行记录 API 路由
def api_runs(limit: int = 20, user=Depends(get_current_user("viewer"))) -> dict[str, Any]:  # 运行记录 API
    """返回最近的运行记录，需登录。"""  # 中文说明

    with sched_session_scope() as session:  # 打开 Session
        rows = (
            session.query(JobRun)
            .order_by(JobRun.started_at.desc())
            .limit(limit)
            .all()
        )  # 查询记录
        data = [
            {
                "id": row.id,
                "profile_id": row.profile_id,
                "status": row.status,
                "started_at": row.started_at.isoformat(),
                "finished_at": row.finished_at.isoformat() if row.finished_at else None,
                "emitted": row.emitted_articles,
                "success": row.delivered_success,
                "failed": row.delivered_failed,
                "error": row.error,
            }
            for row in rows
        ]  # 组装数据
    return {"items": data}  # 返回 JSON


@app.get("/api/prompt-experiments")  # Prompt 实验数据路由
def api_prompt_experiments(user=Depends(get_current_user("viewer"))) -> Dict[str, Any]:  # Prompt 实验 API
    """返回各 Prompt Variant 的命中率与质量评分。"""  # 中文说明

    with main_session_scope() as session:  # 打开主库 Session
        return _collect_prompt_experiment_stats(session)  # 计算并返回


@app.get("/api/prompt-experiments/export")  # Prompt 实验 CSV 导出
def api_prompt_experiments_export(user=Depends(get_current_user("viewer"))) -> Response:  # Prompt 导出 API
    """将 Prompt 实验统计导出为 CSV。"""  # 中文说明

    with main_session_scope() as session:  # 打开主库 Session
        data = _collect_prompt_experiment_stats(session)  # 聚合数据
    buffer = StringIO()  # 准备内存缓冲
    writer = csv.writer(buffer)  # 构造 CSV writer
    writer.writerow(["variant", "hit_rate", "avg_quality", "avg_fallback", "count"])  # 写入表头
    for item in data["items"]:  # 遍历每个 Variant
        writer.writerow(
            [
                item["variant"],
                f"{item['hit_rate']:.2%}",
                f"{item['avg_quality']:.2f}",
                f"{item['avg_fallback']:.2f}",
                item["count"],
            ]
        )  # 写入数据行
    response = Response(content=buffer.getvalue(), media_type="text/csv")  # 构造响应
    response.headers["Content-Disposition"] = "attachment; filename=prompt_experiments.csv"  # 设置下载文件名
    return response


@app.get("/api/schedules")  # 调度列表路由
def api_schedules(user=Depends(get_current_user("viewer"))) -> dict[str, Any]:  # 调度列表
    """调用调度 API 返回全部调度信息。"""  # 中文说明

    return {"items": list_schedules()}  # 返回数据


@app.post("/api/schedules/{schedule_id}/pause")  # 暂停调度路由
def api_pause_schedule(schedule_id: int, user=Depends(get_current_user("admin"))) -> dict[str, str]:  # 暂停调度
    """暂停指定调度，仅管理员可调用。"""  # 中文说明

    pause_schedule(schedule_id)  # 调用暂停
    return {"status": "paused"}  # 返回状态


@app.post("/api/schedules/{schedule_id}/resume")  # 恢复调度路由
def api_resume_schedule(schedule_id: int, user=Depends(get_current_user("admin"))) -> dict[str, str]:  # 恢复调度
    """恢复指定调度，仅管理员可调用。"""  # 中文说明

    resume_schedule(schedule_id)  # 调用恢复
    return {"status": "resumed"}  # 返回状态


@app.post("/api/run-now")  # 立即执行路由
def api_run_now(payload: dict[str, Any], user=Depends(get_current_user("operator"))) -> dict[str, str]:  # 立即执行
    """立即触发 Profile 运行，管理员或操作员可用。"""  # 中文说明

    profile_id = payload.get("profile_id")  # 读取 Profile ID
    if profile_id is None:  # 未提供
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Missing profile_id")  # 抛出异常
    run_now(profile_id)  # 调用执行
    return {"status": "triggered"}  # 返回状态


@app.get("/api/metrics/summary")  # 指标摘要路由
def api_metrics_summary(days: int = 7, user=Depends(get_current_user("viewer"))) -> dict[str, Any]:  # 指标摘要
    """统计近 N 天的指标，用于仪表盘展示。"""  # 中文说明

    cutoff = None  # 初始化占位符  # 中文说明
    from datetime import datetime, timedelta  # 局部导入时间工具  # 中文说明

    cutoff = datetime.utcnow() - timedelta(days=days)  # 计算时间窗口
    with sched_session_scope() as session:  # 打开 Session
        rows = (
            session.query(MetricEvent)
            .filter(MetricEvent.ts >= cutoff)
            .order_by(MetricEvent.ts.desc())
            .all()
        )  # 查询指标
        total_success = sum(1 for row in rows if row.kind == "delivery" and row.key == "platform_success")  # 成功次数
        total_error = sum(1 for row in rows if row.kind == "error")  # 错误次数
    return {"success": total_success, "errors": total_error}  # 返回摘要


@app.post("/api/ingest/log")  # 日志上报路由
async def api_ingest_log(request: Request) -> Response:  # 日志上报
    """接收客户端日志，上报仅在允许远程时开放。"""  # 中文说明

    if not settings.dashboard_enable_remote and request.client.host not in {"127.0.0.1", "::1"}:  # 校验来源
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="remote ingest disabled")  # 拒绝
    await request.json()  # 消费请求体
    return JSONResponse({"status": "ok"})  # 返回成功


@app.post("/api/ingest/metric")  # 指标上报路由
async def api_ingest_metric(request: Request) -> Response:  # 指标上报
    """接收客户端指标数据，当前版本仅记录请求成功。"""  # 中文说明

    if not settings.dashboard_enable_remote and request.client.host not in {"127.0.0.1", "::1"}:  # 校验来源
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="remote ingest disabled")  # 拒绝
    await request.json()  # 消费请求体
    return JSONResponse({"status": "ok"})  # 返回成功


@app.get("/login", response_class=HTMLResponse)  # 登录页面路由
def page_login(request: Request) -> HTMLResponse:  # 登录页面
    """返回登录页面模板。"""  # 中文说明

    context = {  # 构造模板上下文
        "request": request,  # 传入请求对象
        "oidc_enabled": settings.oidc_enable,  # 提供 OIDC 开关状态
        "oidc_login_url": "/auth/oidc/login",  # 提供统一的 OIDC 登录入口
    }
    return TEMPLATES.TemplateResponse("login.html", context)  # 渲染模板


@app.get("/", response_class=HTMLResponse)  # 首页路由
def page_index(request: Request) -> HTMLResponse:  # 总览页面
    """渲染仪表盘首页，使用前端 fetch 调用 API。"""  # 中文说明

    return TEMPLATES.TemplateResponse("index.html", {"request": request})  # 渲染模板


@app.get("/prompt-experiments", response_class=HTMLResponse)  # Prompt 实验页面
def page_prompt_experiments(request: Request, user=Depends(get_current_user("viewer"))) -> HTMLResponse:  # 页面入口
    """渲染 Prompt 实验展示页面。"""  # 中文说明

    return TEMPLATES.TemplateResponse("prompt_experiments.html", {"request": request})  # 渲染模板


@app.get("/runs", response_class=HTMLResponse)  # 运行列表页面路由
def page_runs(request: Request) -> HTMLResponse:  # 运行列表页面
    """展示运行记录表格。"""  # 中文说明

    return TEMPLATES.TemplateResponse("runs.html", {"request": request})  # 渲染模板


@app.get("/schedules", response_class=HTMLResponse)  # 调度管理页面路由
def page_schedules(request: Request) -> HTMLResponse:  # 调度管理页面
    """展示调度列表与操作按钮。"""  # 中文说明

    return TEMPLATES.TemplateResponse("schedules.html", {"request": request})  # 渲染模板


@app.get("/review", response_class=HTMLResponse)
def page_review(request: Request, user=Depends(get_current_user("operator"))) -> HTMLResponse:
    """渲染人工复核工作台页面。"""

    context = {
        "request": request,
        "auto_deliver": settings.qa_approve_autodeliver,
    }
    return TEMPLATES.TemplateResponse("review_queue.html", context)


def run() -> None:  # 启动函数
    """解析配置并使用 uvicorn 启动服务。"""  # 中文说明

    host, port = settings.dashboard_bind.split(":")  # 拆分绑定地址
    import uvicorn  # 延迟导入 uvicorn  # 中文注释

    uvicorn.run("app.dashboard.server:app", host=host, port=int(port), reload=False)  # 启动服务


if __name__ == "__main__":  # 脚本入口
    run()  # 启动服务
