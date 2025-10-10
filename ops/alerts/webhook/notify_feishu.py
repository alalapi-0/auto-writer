"""飞书 Webhook 通道脚本，用于接收 Alertmanager 告警并推送。"""  # 模块说明

from __future__ import annotations  # 启用未来注解

import asyncio  # 异步工具
import base64  # 编码工具
import hashlib  # 摘要算法
import hmac  # HMAC 算法
import json  # JSON 处理
import os  # 环境变量
import sys  # 标准输入输出
import time  # 时间函数
from typing import Any, Dict, List  # 类型提示

import httpx  # HTTP 客户端
from fastapi import FastAPI, HTTPException, Request  # FastAPI 组件

APP = FastAPI(title="AutoWriter Feishu Alert Relay")  # 创建 FastAPI 应用

WEBHOOK_URL = os.getenv("FEISHU_WEBHOOK_URL", "")  # 飞书 Webhook 地址
SIGNING_SECRET = os.getenv("FEISHU_SIGNING_SECRET", "")  # 飞书签名密钥
TIMEOUT_SECONDS = float(os.getenv("FEISHU_FORWARD_TIMEOUT", "10"))  # 请求超时时间
RETRY_LIMIT = int(os.getenv("FEISHU_FORWARD_RETRIES", "3"))  # 重试次数
RETRY_BACKOFF = float(os.getenv("FEISHU_FORWARD_BACKOFF", "2"))  # 重试退避

async def _post_to_feishu(payload: Dict[str, Any]) -> None:  # 定义发送函数
    """带重试将消息发送到飞书。"""  # 函数说明

    if not WEBHOOK_URL:  # 校验配置
        raise RuntimeError("FEISHU_WEBHOOK_URL 未设置")  # 抛出异常
    last_error: Exception | None = None  # 初始化错误
    for attempt in range(1, RETRY_LIMIT + 1):  # 循环重试
        try:  # 捕获异常
            async with httpx.AsyncClient(timeout=TIMEOUT_SECONDS) as client:  # 创建客户端
                response = await client.post(WEBHOOK_URL, json=payload)  # 发送请求
            response.raise_for_status()  # 检查状态码
            data = response.json()  # 解析返回
            if data.get("code") not in (0, None):  # 校验飞书返回码
                raise RuntimeError(f"飞书返回错误: {data}")  # 抛出错误
            return  # 成功则结束
        except Exception as exc:  # 捕获异常
            last_error = exc  # 记录错误
            await asyncio.sleep(RETRY_BACKOFF * attempt)  # 退避等待
    raise RuntimeError(f"飞书推送失败: {last_error}")  # 超出重试后抛出

def _build_signature(timestamp: str) -> str | None:  # 生成签名
    """根据密钥计算飞书签名。"""  # 函数说明

    if not SIGNING_SECRET:  # 未配置密钥
        return None  # 返回空
    string_to_sign = f"{timestamp}\n{SIGNING_SECRET}"  # 构造待签名字符串
    digest = hmac.new(  # 计算 HMAC
        SIGNING_SECRET.encode("utf-8"),  # 密钥
        string_to_sign.encode("utf-8"),  # 待签名字符串
        digestmod=hashlib.sha256,  # 签名算法
    ).digest()  # 获取摘要
    return base64.b64encode(digest).decode("utf-8")  # 返回 Base64 编码

def _format_alerts(alerts: List[Dict[str, Any]]) -> Dict[str, Any]:  # 构造飞书消息
    """将告警渲染为飞书文本消息。"""  # 函数说明

    lines: List[str] = []  # 初始化文本
    for item in alerts:  # 遍历告警
        status = item.get("status", "unknown")  # 告警状态
        labels = item.get("labels", {})  # 标签
        annotations = item.get("annotations", {})  # 注释
        name = labels.get("alertname", "unknown")  # 告警名称
        severity = labels.get("severity", "unknown")  # 告警级别
        summary = annotations.get("summary") or annotations.get("description") or "无描述"  # 摘要
        url = item.get("generatorURL", "")  # 告警链接
        line = f"[{status}] {name}({severity}) - {summary}"  # 拼接文本
        if url:  # 如有链接
            line += f"\n详情: {url}"  # 附加链接
        lines.append(line)  # 收集文本
    body_text = "\n\n".join(lines) if lines else "未收到告警"  # 合并文本
    timestamp = str(int(time.time()))  # 生成时间戳
    signature = _build_signature(timestamp)  # 计算签名
    message: Dict[str, Any] = {  # 构造消息体
        "msg_type": "text",  # 消息类型
        "content": {"text": body_text},  # 文本内容
    }  # 结构结束
    if signature is not None:  # 如果存在签名
        message.update({"timestamp": timestamp, "sign": signature})  # 附加签名字段
    return message  # 返回消息

@APP.post("/webhook")  # 注册路由
async def handle_alertmanager(request: Request) -> Dict[str, Any]:  # 处理函数
    """接收 Alertmanager Webhook 并推送到飞书。"""  # 函数说明

    payload: Dict[str, Any] = await request.json()  # 解析 JSON
    alerts: List[Dict[str, Any]] = payload.get("alerts", [])  # 提取告警
    message = _format_alerts(alerts)  # 构造消息
    try:  # 捕获异常
        await _post_to_feishu(message)  # 调用发送
    except Exception as exc:  # 捕获失败
        raise HTTPException(status_code=500, detail=str(exc))  # 返回 500
    return {"status": "ok", "forwarded": len(alerts)}  # 返回成功

def main() -> int:  # CLI 主入口
    """支持通过标准输入直接推送飞书。"""  # 函数说明

    try:  # 捕获异常
        data = sys.stdin.read()  # 读取输入
        payload = json.loads(data) if data.strip() else {"alerts": []}  # 解析 JSON
        alerts = payload.get("alerts", [])  # 提取告警
        message = _format_alerts(alerts)  # 构造消息
        asyncio.run(_post_to_feishu(message))  # 执行推送
    except Exception as exc:  # 捕获异常
        print(f"飞书发送失败: {exc}", file=sys.stderr)  # 输出错误
        return 1  # 返回失败码
    return 0  # 返回成功码

if __name__ == "__main__":  # 判断脚本直接执行
    sys.exit(main())  # 以退出码结束
