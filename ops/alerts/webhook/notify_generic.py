"""通用 Webhook 转发脚本，接收 Alertmanager 推送并再次发送。"""  # 模块说明

from __future__ import annotations  # 启用未来注解

import asyncio  # 异步工具
import json  # 处理 JSON
import os  # 读取环境变量
import sys  # 处理标准输入输出
from typing import Any, Dict, List  # 类型提示

import httpx  # HTTP 客户端
from fastapi import FastAPI, HTTPException, Request  # Web 框架组件

APP = FastAPI(title="AutoWriter Generic Alert Relay")  # 创建 FastAPI 应用

TARGET_URL = os.getenv("GENERIC_FORWARD_URL", "")  # 目标 Webhook 地址
TARGET_TOKEN = os.getenv("GENERIC_FORWARD_TOKEN", "")  # 可选 Bearer Token
TIMEOUT_SECONDS = float(os.getenv("GENERIC_FORWARD_TIMEOUT", "10"))  # 请求超时时间
RETRY_LIMIT = int(os.getenv("GENERIC_FORWARD_RETRIES", "3"))  # 重试次数
RETRY_BACKOFF = float(os.getenv("GENERIC_FORWARD_BACKOFF", "2"))  # 重试退避秒数

async def _do_post(payload: Dict[str, Any]) -> None:  # 定义请求函数
    """携带重试将告警发送至下游。"""  # 函数说明

    if not TARGET_URL:  # 校验目标地址
        raise RuntimeError("GENERIC_FORWARD_URL 未设置")  # 抛出异常
    headers = {"Content-Type": "application/json"}  # 基础请求头
    if TARGET_TOKEN:  # 若配置了 Token
        headers["Authorization"] = f"Bearer {TARGET_TOKEN}"  # 加入授权头
    last_error: Exception | None = None  # 初始化错误记录
    for attempt in range(1, RETRY_LIMIT + 1):  # 循环重试
        try:  # 捕获请求异常
            async with httpx.AsyncClient(timeout=TIMEOUT_SECONDS) as client:  # 创建异步客户端
                response = await client.post(TARGET_URL, json=payload, headers=headers)  # 发送请求
            response.raise_for_status()  # 检查状态码
            return  # 成功则直接返回
        except Exception as exc:  # 捕获任意异常
            last_error = exc  # 保存最后一次错误
            await asyncio.sleep(RETRY_BACKOFF * attempt)  # 指数退避
    raise RuntimeError(f"转发失败: {last_error}")  # 超出重试后抛出异常

def _format_alerts(alerts: List[Dict[str, Any]]) -> Dict[str, Any]:  # 定义格式化函数
    """将 Alertmanager 告警列表转换为通用消息体。"""  # 函数说明

    lines: List[str] = []  # 初始化文本行
    for item in alerts:  # 遍历告警
        status = item.get("status", "unknown")  # 告警状态
        labels = item.get("labels", {})  # 标签
        annotations = item.get("annotations", {})  # 注释
        name = labels.get("alertname", "unknown")  # 告警名称
        severity = labels.get("severity", "unknown")  # 告警级别
        summary = annotations.get("summary") or annotations.get("description") or "无描述"  # 文本摘要
        lines.append(f"[{status}] {name}({severity}) - {summary}")  # 组装文本
    body_text = "\n".join(lines) if lines else "未收到告警"  # 合并文本
    return {  # 返回结构化载荷
        "title": "AutoWriter 告警聚合",  # 标题
        "text": body_text,  # 文本内容
        "alert_count": len(alerts),  # 告警数量
        "alerts": alerts,  # 原始数据
    }

@APP.post("/webhook")  # 定义 POST 路由
async def handle_alertmanager(request: Request) -> Dict[str, Any]:  # 路由处理函数
    """接收 Alertmanager Webhook 并转发。"""  # 函数说明

    payload: Dict[str, Any] = await request.json()  # 解析 JSON
    alerts: List[Dict[str, Any]] = payload.get("alerts", [])  # 取出告警
    message = _format_alerts(alerts)  # 格式化消息
    try:  # 捕获异常
        await _do_post(message)  # 发送请求
    except Exception as exc:  # 捕获发送失败
        raise HTTPException(status_code=500, detail=str(exc))  # 返回 500 错误
    return {"status": "ok", "forwarded": len(alerts)}  # 返回成功信息

def main() -> int:  # CLI 主入口
    """支持从标准输入读取告警 JSON 并发送。"""  # 函数说明

    try:  # 捕获解析或发送异常
        data = sys.stdin.read()  # 读取标准输入
        payload = json.loads(data) if data.strip() else {"alerts": []}  # 加载 JSON
        alerts = payload.get("alerts", [])  # 解析告警列表
        message = _format_alerts(alerts)  # 格式化消息
        asyncio.run(_do_post(message))  # 执行发送
    except Exception as exc:  # 捕获异常
        print(f"发送失败: {exc}", file=sys.stderr)  # 输出错误
        return 1  # 返回失败码
    return 0  # 返回成功码

if __name__ == "__main__":  # 脚本直接运行时
    sys.exit(main())  # 以退出码结束
