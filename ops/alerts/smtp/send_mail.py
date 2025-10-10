"""SMTP 邮件通知脚本，将 Alertmanager 告警转换为邮件发送。"""  # 模块说明
from __future__ import annotations  # 启用未来注解
import asyncio  # 异步工具
import json  # JSON 处理
import os  # 环境变量
import smtplib  # SMTP 客户端
import sys  # 标准输入输出
from email.mime.multipart import MIMEMultipart  # 复合邮件
from email.mime.text import MIMEText  # 文本邮件
from typing import Any, Dict, List  # 类型提示
from fastapi import FastAPI, HTTPException, Request  # FastAPI 组件
APP = FastAPI(title="AutoWriter Alert SMTP Relay")  # 创建 FastAPI 应用
SMTP_HOST = os.getenv("ALERT_SMTP_HOST", "")  # SMTP 主机
SMTP_PORT = int(os.getenv("ALERT_SMTP_PORT", "587"))  # SMTP 端口
SMTP_USERNAME = os.getenv("ALERT_SMTP_USERNAME", "")  # SMTP 用户
SMTP_PASSWORD = os.getenv("ALERT_SMTP_PASSWORD", "")  # SMTP 密码
MAIL_FROM = os.getenv("ALERT_EMAIL_FROM", "alerts@example.com")  # 发件人
MAIL_TO = os.getenv("ALERT_EMAIL_TO", "")  # 收件人
MAIL_SUBJECT = os.getenv("ALERT_EMAIL_SUBJECT", "AutoWriter 告警汇总")  # 邮件主题
USE_SSL = os.getenv("ALERT_SMTP_USE_SSL", "false").lower() == "true"  # 是否使用 SSL
USE_STARTTLS = os.getenv("ALERT_SMTP_USE_STARTTLS", "true").lower() == "true"  # 是否启用 STARTTLS
TIMEOUT_SECONDS = float(os.getenv("ALERT_SMTP_TIMEOUT", "10"))  # 超时时间
RETRY_LIMIT = int(os.getenv("ALERT_SMTP_RETRIES", "3"))  # 重试次数
RETRY_BACKOFF = float(os.getenv("ALERT_SMTP_BACKOFF", "2"))  # 退避时间
class SMTPConfigError(RuntimeError):  # 自定义异常
    """用于标记 SMTP 配置不完整的异常。"""  # 异常说明
def _ensure_config() -> None:  # 校验配置
    """在发送前确保 SMTP 配置齐全。"""  # 函数说明
    if not SMTP_HOST or not MAIL_TO:  # 检查必要参数
        raise SMTPConfigError("SMTP 配置缺失，请检查 ALERT_SMTP_HOST/ALERT_EMAIL_TO")  # 抛出异常
def _format_alerts(alerts: List[Dict[str, Any]]) -> Dict[str, str]:  # 格式化告警
    """生成纯文本与 HTML 两种格式的邮件正文。"""  # 函数说明
    if not alerts:  # 无告警时
        text_body = "当前没有告警"  # 纯文本
        html_body = "<p>当前没有告警</p>"  # HTML
    else:  # 存在告警
        lines: List[str] = []  # 纯文本列表
        rows: List[str] = []  # HTML 行列表
        for item in alerts:  # 遍历告警
            status = item.get("status", "unknown")  # 状态
            labels = item.get("labels", {})  # 标签
            annotations = item.get("annotations", {})  # 注释
            name = labels.get("alertname", "unknown")  # 名称
            severity = labels.get("severity", "unknown")  # 严重级别
            summary = annotations.get("summary") or annotations.get("description") or "无描述"  # 摘要
            url = item.get("generatorURL", "")  # 链接
            lines.append(f"[{status}] {name}({severity}) - {summary}")  # 记录文本
            link_html = f'<a href="{url}">详情</a>' if url else "-"  # 链接 HTML
            rows.append(f"<tr><td>{status}</td><td>{name}</td><td>{severity}</td><td>{summary}</td><td>{link_html}</td></tr>")  # 构造表格行
        text_body = "\n".join(lines)  # 合并纯文本
        html_rows = "".join(rows)  # 合并表格行
        html_body = (
            "<table border='1' cellpadding='4' cellspacing='0'>"
            "<thead><tr><th>状态</th><th>名称</th><th>级别</th><th>摘要</th><th>链接</th></tr></thead>"
            f"<tbody>{html_rows}</tbody>"
            "</table>"
        )  # 生成完整表格
    return {"text": text_body, "html": html_body}  # 返回结果

def _build_message(alerts: List[Dict[str, Any]]) -> MIMEMultipart:  # 构造邮件对象
    """根据告警构造 MIME 消息。"""  # 函数说明
    bodies = _format_alerts(alerts)  # 获取正文
    message = MIMEMultipart("alternative")  # 创建多格式邮件
    message["Subject"] = MAIL_SUBJECT  # 设置主题
    message["From"] = MAIL_FROM  # 设置发件人
    message["To"] = MAIL_TO  # 设置收件人
    message.attach(MIMEText(bodies["text"], "plain", "utf-8"))  # 附加纯文本
    message.attach(MIMEText(bodies["html"], "html", "utf-8"))  # 附加 HTML
    return message  # 返回消息
async def _send_mail(message: MIMEMultipart) -> None:  # 定义发送函数
    """使用同步 SMTP 客户端发送邮件并提供重试。"""  # 函数说明
    _ensure_config()  # 校验配置
    last_error: Exception | None = None  # 初始化错误
    for attempt in range(1, RETRY_LIMIT + 1):  # 循环重试
        try:  # 捕获异常
            await asyncio.to_thread(_send_once, message)  # 在线程中执行发送
            return  # 成功后退出
        except Exception as exc:  # 捕获异常
            last_error = exc  # 记录错误
            await asyncio.sleep(RETRY_BACKOFF * attempt)  # 退避等待
    raise RuntimeError(f"邮件发送失败: {last_error}")  # 超出重试后抛出
def _send_once(message: MIMEMultipart) -> None:  # 单次发送函数
    """同步方式发送邮件。"""  # 函数说明
    if USE_SSL:  # 使用 SSL
        server = smtplib.SMTP_SSL(host=SMTP_HOST, port=SMTP_PORT, timeout=TIMEOUT_SECONDS)  # 创建 SSL 客户端
    else:  # 使用普通连接
        server = smtplib.SMTP(host=SMTP_HOST, port=SMTP_PORT, timeout=TIMEOUT_SECONDS)  # 创建客户端
    try:  # 捕获异常
        server.ehlo()  # SMTP 握手
        if not USE_SSL and USE_STARTTLS:  # 如需 STARTTLS
            server.starttls()  # 升级为 TLS
            server.ehlo()  # 再次握手
        if SMTP_USERNAME and SMTP_PASSWORD:  # 如有凭据
            server.login(SMTP_USERNAME, SMTP_PASSWORD)  # 登录
        server.sendmail(MAIL_FROM, [addr.strip() for addr in MAIL_TO.split(',') if addr.strip()], message.as_string())  # 发送邮件
    finally:  # 无论成功失败均执行
        server.quit()  # 关闭连接
@APP.post("/webhook")  # 注册路由
async def handle_alertmanager(request: Request) -> Dict[str, Any]:  # 处理函数
    """接收 Alertmanager Webhook 并通过邮件发送。"""  # 函数说明
    payload: Dict[str, Any] = await request.json()  # 解析 JSON
    alerts: List[Dict[str, Any]] = payload.get("alerts", [])  # 提取告警
    message = _build_message(alerts)  # 构造邮件
    try:  # 捕获异常
        await _send_mail(message)  # 发送邮件
    except Exception as exc:  # 捕获失败
        raise HTTPException(status_code=500, detail=str(exc))  # 返回 500
    return {"status": "ok", "forwarded": len(alerts)}  # 返回成功
def main() -> int:  # CLI 主入口
    """支持通过标准输入直接发送邮件。"""  # 函数说明
    try:  # 捕获异常
        data = sys.stdin.read()  # 读取输入
        payload = json.loads(data) if data.strip() else {"alerts": []}  # 解析 JSON
        alerts = payload.get("alerts", [])  # 提取告警
        message = _build_message(alerts)  # 构造邮件
        asyncio.run(_send_mail(message))  # 执行发送
    except Exception as exc:  # 捕获异常
        print(f"邮件发送失败: {exc}", file=sys.stderr)  # 输出错误
        return 1  # 返回失败码
    return 0  # 返回成功码
if __name__ == "__main__":  # 脚本直接执行
    sys.exit(main())  # 以退出码结束
