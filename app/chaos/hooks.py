"""混沌注入工具模块，支持延迟、错误与丢弃三类演练。"""  # 模块中文说明

from __future__ import annotations  # 启用未来注解语法

import random  # 提供概率触发与随机延迟
import time  # 默认使用阻塞睡眠实现延迟
from typing import Callable  # 类型提示睡眠函数

import structlog  # 结构化日志记录

from app.telemetry.metrics import inc_chaos_event  # Prometheus 计数器
from config.settings import settings  # 全局配置对象

LOGGER = structlog.get_logger(__name__)  # 初始化日志器
_RNG = random.Random()  # 独立随机数生成器，便于测试种子控制


class ChaosError(RuntimeError):
    """混沌注入导致的异常，用于模拟系统错误。"""  # 类中文说明


class ChaosDropError(RuntimeError):
    """混沌注入导致的丢弃异常，用于模拟消息落入死信。"""  # 类中文说明


def maybe_inject_chaos(stage: str, sleep_func: Callable[[float], None] | None = None) -> None:
    """根据配置概率性触发混沌事件。"""  # 函数中文说明

    if not getattr(settings, "chaos_enable", False):  # 未开启混沌演练时直接返回
        return  # 不执行任何动作
    probability = float(getattr(settings, "chaos_prob", 0.0))  # 读取注入概率
    if probability <= 0:  # 概率为零表示关闭
        return  # 不执行任何动作
    roll = _RNG.random()  # 投掷概率
    if roll > probability:  # 未命中概率阈值
        return  # 不执行任何动作
    types = getattr(settings, "chaos_types", ["latency", "error", "drop"])  # 读取事件类型列表
    if not types:  # 空列表时无事件可选
        return  # 不执行任何动作
    event_type = _RNG.choice(types)  # 随机抽取事件类型
    inc_chaos_event(event_type, stage)  # 上报混沌事件指标
    LOGGER.warning("chaos_injected", stage=stage, chaos_event=event_type)  # 记录混沌触发日志
    if event_type == "latency":  # 延迟事件
        sleep = sleep_func or time.sleep  # 选择睡眠函数
        delay = _RNG.uniform(0.5, 2.0)  # 生成延迟秒数
        sleep(delay)  # 执行延迟
        return  # 延迟后继续执行
    if event_type == "error":  # 错误事件
        raise ChaosError(f"混沌注入错误: stage={stage}")  # 抛出异常模拟系统错误
    if event_type == "drop":  # 丢弃事件
        raise ChaosDropError(f"混沌注入丢弃: stage={stage}")  # 抛出异常模拟死信
    LOGGER.info("chaos_event_ignored", stage=stage, chaos_event=event_type)  # 兜底记录未知类型


def seed_rng(seed: int) -> None:
    """为单元测试提供固定随机种子的入口。"""  # 函数中文说明

    _RNG.seed(seed)  # 重置随机数发生器


__all__ = ["maybe_inject_chaos", "ChaosDropError", "ChaosError", "seed_rng"]  # 导出符号
