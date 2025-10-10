"""Prometheus 指标封装，统一初始化与埋点操作。"""  # 模块中文说明

from __future__ import annotations  # 启用未来注解语法

from typing import Tuple  # 引入类型别名便于返回值描述

from prometheus_client import (  # 导入 Prometheus 客户端核心工具
    CONTENT_TYPE_LATEST,  # 指标响应的标准 Content-Type
    CollectorRegistry,  # 指标注册表类型
    Counter,  # 计数器类型
    Histogram,  # 直方图类型
    generate_latest,  # 序列化指标的函数
)  # 导入结束

from config.settings import settings  # 引入全局配置对象

PROMETHEUS_ENABLED: bool = getattr(settings, "PROMETHEUS_ENABLED", True)  # 读取配置开关，默认为开启

_REGISTRY: CollectorRegistry | None = CollectorRegistry() if PROMETHEUS_ENABLED else None  # 根据开关初始化注册表

if PROMETHEUS_ENABLED:  # 当 Prometheus 功能启用时注册指标
    _RUN_COUNTER: Counter = Counter(  # 定义运行计数器
        "autowriter_runs_total",  # 指标名称
        "AutoWriter 作业整体执行次数",  # 指标帮助文本
        labelnames=("status", "profile"),  # 指标标签
        registry=_REGISTRY,  # 绑定到自建注册表
    )  # 计数器定义结束
    _GENERATION_COUNTER: Counter = Counter(  # 定义生成次数计数器
        "autowriter_generation_total",  # 指标名称
        "AutoWriter 成功生成稿件的次数",  # 指标帮助文本
        labelnames=("profile",),  # 标签仅包含 profile
        registry=_REGISTRY,  # 绑定注册表
    )  # 计数器定义结束
    _DELIVERY_COUNTER: Counter = Counter(  # 定义发布计数器
        "autowriter_delivery_total",  # 指标名称
        "AutoWriter 各平台投递结果次数",  # 指标帮助文本
        labelnames=("platform", "status"),  # 标签包含平台与状态
        registry=_REGISTRY,  # 绑定注册表
    )  # 计数器定义结束
    _RATE_LIMIT_COUNTER: Counter = Counter(  # 定义限速触发计数器
        "autowriter_rate_limit_total",  # 指标名称
        "AutoWriter 平台限速触发次数",  # 指标帮助文本
        labelnames=("platform", "reason"),  # 标签包含平台与触发原因
        registry=_REGISTRY,  # 绑定注册表
    )  # 计数器定义结束
    _LATENCY_HISTOGRAM: Histogram = Histogram(  # 定义作业耗时直方图
        "autowriter_job_latency_seconds",  # 指标名称
        "AutoWriter 作业从调度到发布的耗时分布",  # 指标帮助文本
        labelnames=("profile",),  # 标签包含 profile
        registry=_REGISTRY,  # 绑定注册表
    )  # 直方图定义结束
    _PLUGIN_ERROR_COUNTER: Counter = Counter(  # 定义插件错误计数器
        "autowriter_plugin_errors_total",  # 指标名称
        "AutoWriter 插件执行报错次数",  # 指标帮助文本
        labelnames=("plugin",),  # 标签包含插件名称
        registry=_REGISTRY,  # 绑定注册表
    )  # 计数器定义结束
    _CHAOS_COUNTER: Counter = Counter(  # 定义混沌事件计数器
        "autowriter_chaos_events_total",  # 指标名称
        "AutoWriter 混沌注入事件统计",  # 指标帮助文本
        labelnames=("type", "stage"),  # 标签包含事件类型与阶段
        registry=_REGISTRY,  # 绑定注册表
    )  # 计数器定义结束
else:  # 当 Prometheus 功能关闭时
    _RUN_COUNTER = None  # 运行计数器占位
    _GENERATION_COUNTER = None  # 生成计数器占位
    _DELIVERY_COUNTER = None  # 投递计数器占位
    _RATE_LIMIT_COUNTER = None  # 限速计数器占位
    _LATENCY_HISTOGRAM = None  # 耗时直方图占位
    _PLUGIN_ERROR_COUNTER = None  # 插件错误计数器占位
    _CHAOS_COUNTER = None  # 混沌计数器占位


def inc_run(status: str, profile: str) -> None:  # 定义运行计数递增函数
    """记录一次调度任务执行结果。"""  # 函数中文文档

    if not PROMETHEUS_ENABLED or _RUN_COUNTER is None:  # 功能关闭时直接返回
        return  # 不执行任何操作
    _RUN_COUNTER.labels(status=status, profile=profile).inc()  # 为对应标签递增一次


def inc_generation(profile: str) -> None:  # 定义生成计数递增函数
    """记录一次稿件生成成功。"""  # 函数中文文档

    if not PROMETHEUS_ENABLED or _GENERATION_COUNTER is None:  # 功能关闭时直接返回
        return  # 不执行任何操作
    _GENERATION_COUNTER.labels(profile=profile).inc()  # 为指定 Profile 递增一次


def inc_delivery(platform: str, status: str) -> None:  # 定义投递计数递增函数
    """记录一次平台投递的结果状态。"""  # 函数中文文档

    if not PROMETHEUS_ENABLED or _DELIVERY_COUNTER is None:  # 功能关闭时直接返回
        return  # 不执行任何操作
    _DELIVERY_COUNTER.labels(platform=platform, status=status).inc()  # 为对应平台与状态递增


def inc_rate_limit(platform: str, reason: str) -> None:  # 定义限速触发递增函数
    """记录一次限速或时间窗等待事件。"""  # 函数中文文档

    if not PROMETHEUS_ENABLED or _RATE_LIMIT_COUNTER is None:  # 功能关闭时直接返回
        return  # 不执行任何操作
    _RATE_LIMIT_COUNTER.labels(platform=platform, reason=reason).inc()  # 根据平台与原因递增


def observe_latency(profile: str, seconds: float) -> None:  # 定义耗时观测函数
    """记录完整作业的耗时数据。"""  # 函数中文文档

    if not PROMETHEUS_ENABLED or _LATENCY_HISTOGRAM is None:  # 功能关闭时直接返回
        return  # 不执行任何操作
    _LATENCY_HISTOGRAM.labels(profile=profile).observe(seconds)  # 在直方图中记录一次观测值


def inc_plugin_error(plugin: str) -> None:  # 定义插件错误计数递增函数
    """记录插件执行报错事件。"""  # 函数中文文档

    if not PROMETHEUS_ENABLED or _PLUGIN_ERROR_COUNTER is None:  # 功能关闭时直接返回
        return  # 不执行任何操作
    _PLUGIN_ERROR_COUNTER.labels(plugin=plugin).inc()  # 为指定插件递增错误计数


def inc_chaos_event(event_type: str, stage: str) -> None:  # 定义混沌事件递增函数
    """记录一次混沌注入事件，便于评估演练频率。"""  # 函数中文文档

    if not PROMETHEUS_ENABLED or _CHAOS_COUNTER is None:  # 功能关闭时直接返回
        return  # 不执行任何操作
    _CHAOS_COUNTER.labels(type=event_type, stage=stage).inc()  # 根据类型与阶段递增


def generate_latest_metrics() -> Tuple[bytes, str]:  # 定义序列化指标的辅助函数
    """返回 Prometheus 指标的字节串与 Content-Type。"""  # 函数中文文档

    if not PROMETHEUS_ENABLED or _REGISTRY is None:  # 功能关闭时返回空内容
        return b"", "text/plain; version=0.0.4; charset=utf-8"  # 返回空指标与默认类型
    return generate_latest(_REGISTRY), CONTENT_TYPE_LATEST  # 调用官方方法序列化注册表


__all__ = [  # 导出模块内公开符号
    "PROMETHEUS_ENABLED",  # 暴露配置开关
    "generate_latest_metrics",  # 暴露指标序列化函数
    "inc_delivery",  # 暴露投递计数函数
    "inc_rate_limit",  # 暴露限速计数函数
    "inc_generation",  # 暴露生成计数函数
    "inc_plugin_error",  # 暴露插件错误计数函数
    "inc_chaos_event",  # 暴露混沌事件计数函数
    "inc_run",  # 暴露运行计数函数
    "observe_latency",  # 暴露耗时观测函数
]  # 导出列表结束
