"""Slack Webhook 通道脚本，负责接收 Alertmanager 告警并推送。"""  # 模块说明

from __future__ import annotations  # 启用未来注解

import asyncio  # 异步工具
import json  # JSON 处理
import os  # 环境变量
import sys  # 标准输入输出
from typing import Any, Dict, List  # 类型提示

import httpx  # HTTP 客户端
from fastapi import FastAPI, HTTPException, Request  # FastAPI 组件

APP = FastAPI(title="AutoWriter Slack Alert Relay")  # 创建 FastAPI 应用

WEBHOOK_URL = os.getenv("SLACK_WEBHOOK_URL", "")  # Slack Webhook 地址
USERNAME = os.getenv("SLACK_USERNAME", "AutoWriter Bot")  # 可选用户名
CHANNEL = os.getenv("SLACK_CHANNEL", "")  # 可选频道
TIMEOUT_SECONDS = float(os.getenv("SLACK_FORWARD_TIMEOUT", "10"))  # 请求超时时间
RETRY_LIMIT = int(os.getenv("SLACK_FORWARD_RETRIES", "3"))  # 重试次数
RETRY_BACKOFF = float(os.getenv("SLACK_FORWARD_BACKOFF", "2"))  # 重试退避

async def _post_to_slack(payload: Dict[str, Any]) -> None:  # 定义发送函数
    """带重试向 Slack 推送消息。"""  # 函数说明

    if not WEBHOOK_URL:  # 校验配置
        raise RuntimeError("SLACK_WEBHOOK_URL 未设置")  # 抛出异常
    last_error: Exception | None = None  # 初始化错误
    for attempt in range(1, RETRY_LIMIT + 1):  # 循环重试
        try:  # 捕获异常
            async with httpx.AsyncClient(timeout=TIMEOUT_SECONDS) as client:  # 创建客户端
                response = await client.post(WEBHOOK_URL, json=payload)  # 发送请求
            response.raise_for_status()  # 检查状态码
            return  # 成功返回
        except Exception as exc:  # 捕获失败
            last_error = exc  # 保存错误
            await asyncio.sleep(RETRY_BACKOFF * attempt)  # 退避等待
    raise RuntimeError(f"Slack 推送失败: {last_error}")  # 超出重试后抛出

def _format_alerts(alerts: List[Dict[str, Any]]) -> Dict[str, Any]:  # 构造 Slack 消息
    """将告警渲染为 Slack Block Kit 结构。"""  # 函数说明

    blocks: List[Dict[str, Any]] = []  # 初始化块
    if alerts:  # 有告警时
        for item in alerts:  # 遍历告警
            status = item.get("status", "unknown")  # 状态
            labels = item.get("labels", {})  # 标签
            annotations = item.get("annotations", {})  # 注释
            name = labels.get("alertname", "unknown")  # 名称
            severity = labels.get("severity", "unknown")  # 严重级别
            summary = annotations.get("summary") or annotations.get("description") or "无描述"  # 摘要
            url = item.get("generatorURL", "")  # 链接
            block_text = f"*{name}* ({severity}) - {status}\n{summary}"  # 组装文本
            if url:  # 如有链接
                block_text += f"\n<{url}|详情>"  # 添加链接
            blocks.append({  # 添加段落
                "type": "section",  # Block 类型
                "text": {"type": "mrkdwn", "text": block_text},  # Markdown 文本
            })  # 结束 block
            blocks.append({"type": "divider"})  # 添加分割线
        blocks.pop()  # 移除最后一条分割线
    else:  # 没有告警时
        blocks.append({  # 添加提示
            "type": "section",  # Block 类型
            "text": {"type": "mrkdwn", "text": "当前没有告警"},  # 文本内容
        })  # 结束提示块
    message: Dict[str, Any] = {  # 构造最终消息
        "username": USERNAME,  # 自定义用户名
        "blocks": blocks,  # 块内容
    }  # 结束结构
    if CHANNEL:  # 若指定频道
        message["channel"] = CHANNEL  # 添加频道
    return message  # 返回消息

@APP.post("/webhook")  # 注册路由
async def handle_alertmanager(request: Request) -> Dict[str, Any]:  # 处理函数
    """接收 Alertmanager Webhook 并推送到 Slack。"""  # 函数说明

    payload: Dict[str, Any] = await request.json()  # 解析 JSON
    alerts: List[Dict[str, Any]] = payload.get("alerts", [])  # 提取告警
    message = _format_alerts(alerts)  # 构造消息
    try:  # 捕获异常
        await _post_to_slack(message)  # 发送
    except Exception as exc:  # 捕获失败
        raise HTTPException(status_code=500, detail=str(exc))  # 返回 500
    return {"status": "ok", "forwarded": len(alerts)}  # 返回成功

def main() -> int:  # CLI 主入口
    """支持通过标准输入直接推送 Slack。"""  # 函数说明

    try:  # 捕获异常
        data = sys.stdin.read()  # 读取输入
        payload = json.loads(data) if data.strip() else {"alerts": []}  # 解析 JSON
        alerts = payload.get("alerts", [])  # 提取告警
        message = _format_alerts(alerts)  # 构造消息
        asyncio.run(_post_to_slack(message))  # 执行发送
    except Exception as exc:  # 捕获异常
        print(f"Slack 发送失败: {exc}", file=sys.stderr)  # 输出错误
        return 1  # 返回失败码
    return 0  # 返回成功码

if __name__ == "__main__":  # 脚本直接执行
    sys.exit(main())  # 以退出码结束
