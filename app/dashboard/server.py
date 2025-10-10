"""Dashboard FastAPI 服务，提供页面与 API。"""  # 模块说明

from __future__ import annotations  # 启用未来注解语法

from pathlib import Path  # 处理路径
from typing import Any  # 类型提示

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
from app.db.migrate_sched import run_migrations, sched_session_scope  # 调度数据库工具
from app.db.models_sched import JobRun, MetricEvent, Schedule, User  # ORM 模型
from app.dispatch.api import router as dispatch_router  # 分发队列路由
from app.dispatch.store import run_dispatch_migrations  # 分发库迁移
from app.scheduler.api import list_schedules, pause_schedule, resume_schedule, run_now  # 调度控制
from app.utils.logger import get_logger  # 日志工具
from app.telemetry.metrics import (  # Prometheus 指标工具
    PROMETHEUS_ENABLED,  # 指标开关
    generate_latest_metrics,  # 序列化指标函数
)  # 导入结束

LOGGER = get_logger(__name__)  # 初始化日志

app = FastAPI(title="AutoWriter Dashboard")  # 创建 FastAPI 应用

TEMPLATES = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))  # 模板目录
app.mount("/static", StaticFiles(directory=str(Path(__file__).parent / "static")), name="static")  # 挂载静态目录
app.include_router(oidc_router)  # 注册 OIDC 相关路由
app.include_router(dispatch_router)  # 注册分发队列路由


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


@app.get("/runs", response_class=HTMLResponse)  # 运行列表页面路由
def page_runs(request: Request) -> HTMLResponse:  # 运行列表页面
    """展示运行记录表格。"""  # 中文说明

    return TEMPLATES.TemplateResponse("runs.html", {"request": request})  # 渲染模板


@app.get("/schedules", response_class=HTMLResponse)  # 调度管理页面路由
def page_schedules(request: Request) -> HTMLResponse:  # 调度管理页面
    """展示调度列表与操作按钮。"""  # 中文说明

    return TEMPLATES.TemplateResponse("schedules.html", {"request": request})  # 渲染模板


def run() -> None:  # 启动函数
    """解析配置并使用 uvicorn 启动服务。"""  # 中文说明

    host, port = settings.dashboard_bind.split(":")  # 拆分绑定地址
    import uvicorn  # 延迟导入 uvicorn  # 中文注释

    uvicorn.run("app.dashboard.server:app", host=host, port=int(port), reload=False)  # 启动服务


if __name__ == "__main__":  # 脚本入口
    run()  # 启动服务
