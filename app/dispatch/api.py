"""FastAPI 路由：提供任务分发相关接口。"""  # 模块中文说明

from __future__ import annotations  # 启用未来注解语法

import json  # 处理 JSON
from datetime import datetime  # 解析时间
from typing import Any, Dict, List  # 类型提示

from fastapi import APIRouter, Depends, Header, HTTPException, status  # FastAPI 工具
from pydantic import BaseModel, Field  # 数据模型

from config.settings import settings  # 配置
from app.dispatch import service  # 业务逻辑
from app.utils.logger import get_logger  # 日志

LOGGER = get_logger(__name__)  # 初始化日志

router = APIRouter(prefix="/api/dispatch", tags=["dispatch"])  # 创建路由对象


class PushRequest(BaseModel):  # 入队请求模型
    profile_id: int = Field(..., description="Profile 主键")  # Profile ID
    payload: Dict[str, Any] = Field(..., description="任务负载")  # 任务负载
    priority: int = Field(0, description="优先级，值越大越靠前")  # 优先级
    available_at: datetime | None = Field(None, description="可领取时间")  # 可领取时间
    max_attempts: int | None = Field(None, description="最大重试次数")  # 最大尝试次数
    idempotency_key: str | None = Field(None, description="幂等键")  # 幂等键


class LeaseRequest(BaseModel):  # 租约请求模型
    agent_name: str = Field(..., description="Worker 名称")  # Worker 名称
    limit: int = Field(1, ge=1, le=50, description="本次最多领取的任务数量")  # 限制数量


class CompleteRequest(BaseModel):  # 完成请求模型
    task_id: int = Field(..., description="任务 ID")  # 任务 ID
    job_run_id: int | None = Field(None, description="对应的 JobRun ID")  # JobRun ID
    emitted_articles: int = Field(0, description="生成文章数")  # 生成数量
    delivered_success: int = Field(0, description="投递成功数")  # 投递成功
    delivered_failed: int = Field(0, description="投递失败数")  # 投递失败
    meta: Dict[str, Any] | None = Field(None, description="附加元信息")  # 附加信息
    agent_name: str = Field(..., description="Worker 名称")  # Worker 名称


class FailRequest(BaseModel):  # 失败请求模型
    task_id: int = Field(..., description="任务 ID")  # 任务 ID
    error: str = Field(..., description="错误描述")  # 错误信息
    agent_name: str = Field(..., description="Worker 名称")  # Worker 名称


class HeartbeatRequest(BaseModel):  # 心跳请求模型
    agent_name: str = Field(..., description="Worker 名称")  # Worker 名称
    meta: Dict[str, Any] | None = Field(None, description="附加元数据")  # 附加信息


def _require_worker_token(authorization: str | None = Header(default=None)) -> None:  # 校验 Worker Token
    """验证 Authorization 头，确保请求来自受信任的 Worker。"""  # 中文说明

    LOGGER.debug(
        "验证 Worker Token 配置=%s header=%s", bool(settings.worker_auth_token), authorization
    )  # 输出调试信息
    if not settings.worker_auth_token:  # 未配置 token
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="worker auth disabled")  # 抛出异常
    if not authorization or not authorization.lower().startswith("bearer "):  # 缺少头或格式错误
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="missing bearer token")  # 抛出异常
    token = authorization.split(" ", 1)[1]  # 解析 token
    if token != settings.worker_auth_token:  # 校验失败
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid worker token")  # 抛出异常
    return None  # 仅用于校验，不返回值


@router.post("/push")  # 注册入队接口
def push_task(payload: PushRequest) -> Dict[str, Any]:  # 入队处理函数
    """内部调用：向队列新增任务，支持幂等控制。"""  # 中文说明

    record = service.enqueue_task(
        profile_id=payload.profile_id,
        payload=payload.payload,
        priority=payload.priority,
        available_at=payload.available_at,
        max_attempts=payload.max_attempts,
        idempotency_key=payload.idempotency_key,
    )  # 执行业务逻辑
    return {
        "task_id": record.id,
        "status": record.status,
        "attempts": record.attempts,
        "max_attempts": record.max_attempts,
    }  # 返回任务信息


@router.post("/lease")  # 注册租约接口
def lease_tasks(payload: LeaseRequest, _: None = Depends(_require_worker_token)) -> Dict[str, List[Dict[str, Any]]]:  # 租约处理函数
    """Worker 调用：领取待执行的任务列表。"""  # 中文说明

    tasks = service.lease_tasks(agent_name=payload.agent_name, limit=payload.limit)  # 调用租约逻辑
    LOGGER.info("Worker=%s 租约数量=%s", payload.agent_name, len(tasks))  # 记录租约数量
    items = []  # 准备返回列表
    for task in tasks:  # 遍历任务
        items.append(
            {
                "task_id": task.id,
                "profile_id": task.profile_id,
                "attempts": task.attempts,
                "max_attempts": task.max_attempts,
                "payload": json.loads(task.payload_json),
                "lease_until": task.lease_until.isoformat() if task.lease_until else None,
            }
        )  # 序列化任务
    return {"items": items}  # 返回任务列表


@router.post("/complete")  # 注册完成接口
def complete_task(payload: CompleteRequest, _: None = Depends(_require_worker_token)) -> Dict[str, Any]:  # 完成处理函数
    """Worker 调用：标记任务成功完成。"""  # 中文说明

    result = {
        "job_run_id": payload.job_run_id,
        "emitted_articles": payload.emitted_articles,
        "delivered_success": payload.delivered_success,
        "delivered_failed": payload.delivered_failed,
        "meta": payload.meta or {},
    }  # 组装结果
    task = service.complete_task(task_id=payload.task_id, agent_name=payload.agent_name, result=result)  # 更新任务
    return {"task_id": task.id, "status": task.status}  # 返回状态


@router.post("/fail")  # 注册失败接口
def fail_task(payload: FailRequest, _: None = Depends(_require_worker_token)) -> Dict[str, Any]:  # 失败处理函数
    """Worker 调用：报告任务执行失败。"""  # 中文说明

    task = service.fail_task(task_id=payload.task_id, agent_name=payload.agent_name, error=payload.error)  # 执行业务逻辑
    return {
        "task_id": task.id,
        "status": task.status,
        "next_available_at": task.available_at.isoformat() if task.available_at else None,
        "attempts": task.attempts,
        "max_attempts": task.max_attempts,
    }  # 返回状态


@router.post("/heartbeat")  # 注册心跳接口
def heartbeat(payload: HeartbeatRequest, _: None = Depends(_require_worker_token)) -> Dict[str, str]:  # 心跳处理函数
    """Worker 调用：上报自身存活状态。"""  # 中文说明

    service.record_heartbeat(agent_name=payload.agent_name, meta=payload.meta)  # 写入心跳
    return {"status": "ok"}  # 返回成功


@router.get("/summary")  # 注册队列汇总接口
def dispatch_summary() -> Dict[str, Any]:  # 队列统计处理函数
    """Dashboard 使用：返回队列状态与 Worker 心跳信息。"""  # 中文说明

    stats = service.get_queue_stats()  # 获取队列统计
    heartbeats = service.list_heartbeats()  # 获取心跳
    return {"queue": stats, "heartbeats": heartbeats}  # 返回综合信息
