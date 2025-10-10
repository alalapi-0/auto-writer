"""遥测客户端，实现本地落库与可选远程上报。"""  # 模块中文说明

from __future__ import annotations  # 启用未来注解语法

from collections import deque  # 使用 deque 作为环形缓冲
from datetime import datetime, timezone  # 处理时间戳
from typing import Deque, Dict  # 类型提示

import httpx  # HTTP 客户端
from zoneinfo import ZoneInfo  # 处理时区

from config.settings import settings  # 引入全局配置
from app.db.migrate_sched import sched_session_scope  # 调度库 Session 上下文
from app.db.models_sched import MetricEvent  # 指标事件 ORM 模型
from app.utils.logger import get_logger  # 日志工具

LOGGER = get_logger(__name__)  # 初始化日志记录器

_METRIC_BUFFER: Deque[Dict] = deque(maxlen=settings.metrics_buffer_max)  # 创建本地缓冲队列
_LOCAL_TZ = ZoneInfo(settings.tz)  # 根据配置初始化本地时区


def _utc_naive_now() -> datetime:  # 生成朴素 UTC 时间
    """按照配置时区取当前时间后转换为 UTC 朴素时间。"""  # 中文说明

    return datetime.now(_LOCAL_TZ).astimezone(timezone.utc).replace(tzinfo=None)  # 生成时区时间并转换


def emit_metric(kind: str, key: str, value: float, profile_id: int | None = None, platform: str | None = None) -> None:  # 定义指标上报函数
    """记录指标事件到本地数据库，并视配置尝试远程上报。"""  # 中文说明

    event = {  # 构造事件字典
        "ts": _utc_naive_now(),
        "kind": kind,
        "profile_id": profile_id,
        "platform": platform,
        "key": key,
        "value": value,
    }
    _METRIC_BUFFER.append(event)  # 推入缓冲
    LOGGER.debug("缓冲指标事件 key=%s size=%s", key, len(_METRIC_BUFFER))  # 记录缓冲大小
    _persist_metrics()  # 将事件写入数据库
    if settings.dashboard_enable_remote:  # 判断是否需要远程上报
        _try_remote_flush()  # 触发远程上报


def emit_log(event: Dict) -> None:  # 定义日志事件函数
    """暂存日志事件，当前版本主要写入调度库供 Dashboard 查询。"""  # 中文说明

    LOGGER.info("日志事件 profile=%s message=%s", event.get("profile_id"), event.get("message"))  # 简单记录
    # 简化实现：日志事件暂未落库，仅供后续扩展。  # 提示说明


def _persist_metrics() -> None:  # 定义内部持久化函数
    """将缓冲中的指标事件批量写入数据库。"""  # 中文说明

    if not _METRIC_BUFFER:  # 若缓冲为空
        return  # 直接返回
    with sched_session_scope() as session:  # 打开 Session
        while _METRIC_BUFFER:  # 循环写入
            payload = _METRIC_BUFFER.popleft()  # 取出事件
            record = MetricEvent(  # 创建 ORM 实例
                ts=payload["ts"],
                kind=payload["kind"],
                profile_id=payload["profile_id"],
                platform=payload["platform"],
                key=payload["key"],
                value=payload["value"],
            )
            session.add(record)  # 添加到 Session
        LOGGER.debug("指标事件已写入数据库")  # 写入完成日志


def _try_remote_flush() -> None:  # 定义远程上报函数
    """若配置允许，尝试向 Dashboard 的 ingest 接口发送事件。"""  # 中文说明

    try:  # 捕获网络异常
        response = httpx.post(  # 发起 POST 请求
            settings.ingest_endpoint + "/metric",  # 拼接指标上报路径
            json={},  # 简化实现：暂不发送具体内容
            timeout=3.0,  # 请求超时
        )
        if response.status_code >= 400:  # 判断响应状态
            LOGGER.warning("远程指标上报失败 status=%s", response.status_code)  # 记录警告
    except Exception as exc:  # noqa: BLE001  # 捕获所有异常
        LOGGER.debug("远程上报异常 error=%s", exc)  # 记录调试日志
