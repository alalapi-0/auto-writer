"""告警面板视图，提供只读告警列表页面与 API。"""  # 模块说明

from __future__ import annotations  # 启用未来注解

from pathlib import Path  # 处理路径
from typing import Any, Dict, List  # 类型提示

import httpx  # HTTP 客户端
from fastapi import APIRouter, Depends, HTTPException, Query, Request  # FastAPI 组件
from fastapi.responses import HTMLResponse  # HTML 响应
from fastapi.templating import Jinja2Templates  # 模板引擎

from app.auth.security import get_current_user  # 鉴权依赖
from app.utils.logger import get_logger  # 日志工具
from config.settings import settings  # 应用配置

LOGGER = get_logger(__name__)  # 初始化日志记录器

router = APIRouter()  # 创建路由器

TEMPLATES = Jinja2Templates(directory=str(Path(__file__).resolve().parents[1] / "templates"))  # 复用模板目录

async def _fetch_alerts() -> List[Dict[str, Any]]:  # 定义告警拉取函数
    """从 Alertmanager 拉取当前告警列表。"""  # 函数说明

    endpoint = settings.alerts_pull_endpoint  # 读取配置
    timeout = httpx.Timeout(10.0)  # 设置超时时间
    try:  # 捕获网络异常
        async with httpx.AsyncClient(timeout=timeout) as client:  # 创建异步客户端
            response = await client.get(endpoint)  # 发起 GET 请求
        response.raise_for_status()  # 检查状态码
        data = response.json()  # 解析 JSON
    except httpx.HTTPError as exc:  # 捕获 HTTP 异常
        LOGGER.error("拉取告警失败: %s", exc)  # 记录错误日志
        raise HTTPException(status_code=502, detail="无法从 Alertmanager 拉取告警")  # 抛出 502 错误
    items = data if isinstance(data, list) else data.get("data", [])  # 兼容不同结构
    return [item for item in items if isinstance(item, dict)]  # 过滤非法项

def _match_labels(alert: Dict[str, Any], filters: List[str]) -> bool:  # 标签匹配函数
    """根据 key:value 形式的过滤条件检查告警标签。"""  # 函数说明

    if not filters:  # 无过滤条件
        return True  # 总是匹配
    labels: Dict[str, str] = alert.get("labels", {})  # 读取标签
    for item in filters:  # 遍历过滤条件
        if ":" not in item:  # 校验格式
            continue  # 跳过非法条件
        key, expected = item.split(":", 1)  # 拆分 key 与 value
        if labels.get(key) != expected:  # 标签不匹配
            return False  # 立即返回失败
    return True  # 所有条件均匹配

@router.get("/alerts", response_class=HTMLResponse)  # 定义页面路由
async def alerts_page(request: Request, user=Depends(get_current_user("viewer"))) -> HTMLResponse:  # 处理函数
    """渲染只读告警面板页面。"""  # 函数说明

    context = {  # 构造模板上下文
        "request": request,  # 请求对象
        "api_endpoint": "/api/alerts",  # 前端数据接口
    }
    return TEMPLATES.TemplateResponse("alerts.html", context)  # 渲染模板

@router.get("/api/alerts")  # 定义 API 路由
async def alerts_api(  # 函数签名
    labels: List[str] = Query(default=[]),  # 标签过滤条件
    status: str | None = Query(default=None),  # 状态过滤条件
    user=Depends(get_current_user("viewer")),  # 鉴权
) -> Dict[str, Any]:  # 返回类型
    """返回符合条件的告警列表。"""  # 函数说明

    raw_alerts = await _fetch_alerts()  # 拉取告警
    filtered: List[Dict[str, Any]] = []  # 初始化结果列表
    for alert in raw_alerts:  # 遍历告警
        if status and alert.get("status") != status:  # 根据状态过滤
            continue  # 跳过
        if not _match_labels(alert, labels):  # 根据标签过滤
            continue  # 跳过
        filtered.append(  # 将告警转换为轻量结构
            {
                "status": alert.get("status", "unknown"),  # 告警状态
                "labels": alert.get("labels", {}),  # 标签
                "annotations": alert.get("annotations", {}),  # 注释
                "startsAt": alert.get("startsAt"),  # 开始时间
                "endsAt": alert.get("endsAt"),  # 结束时间
                "generatorURL": alert.get("generatorURL"),  # 源链接
            }
        )
    return {"items": filtered, "count": len(filtered)}  # 返回数据
