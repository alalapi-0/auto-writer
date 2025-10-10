"""验证 Prometheus 指标导出与埋点函数。"""  # 模块中文说明

from __future__ import annotations  # 启用未来注解语法

import importlib  # 动态重新加载模块

from fastapi import FastAPI, Response  # 构造最小 API 应用
from fastapi.testclient import TestClient  # FastAPI 测试客户端

from config.settings import settings  # 全局配置对象


def test_metrics_endpoint_exposes_counters() -> None:  # 定义单元测试函数
    """确保埋点函数生效且 /metrics 可以返回指标。"""  # 测试中文说明

    original_flag = getattr(settings, "PROMETHEUS_ENABLED", True)  # 记录原始开关值
    settings.PROMETHEUS_ENABLED = True  # 强制开启 Prometheus 功能
    metrics_module = importlib.reload(importlib.import_module("app.telemetry.metrics"))  # 重新加载指标模块
    app = FastAPI()  # 构建最小化服务以暴露指标

    @app.get("/metrics")
    def metrics_endpoint() -> Response:
        """委托指标模块返回 Prometheus 数据。"""  # 内联说明

        payload, content_type = metrics_module.generate_latest_metrics()  # 生成指标输出
        return Response(payload, media_type=content_type)  # 构造响应
    metrics_module.inc_run("success", "demo")  # 写入运行成功计数
    metrics_module.inc_generation("demo")  # 写入生成计数
    metrics_module.inc_delivery("wechat", "success")  # 写入投递成功计数
    metrics_module.observe_latency("demo", 1.23)  # 写入耗时观测
    metrics_module.inc_plugin_error("demo_plugin")  # 写入插件错误
    client = TestClient(app)  # 创建测试客户端
    response = client.get("/metrics")  # 请求指标路由
    assert response.status_code == 200  # 校验请求成功
    body = response.text  # 提取响应文本
    assert "autowriter_runs_total" in body  # 验证运行计数指标存在
    assert "autowriter_generation_total" in body  # 验证生成计数指标存在
    assert "autowriter_delivery_total" in body  # 验证投递计数指标存在
    assert "autowriter_job_latency_seconds" in body  # 验证耗时直方图存在
    assert "autowriter_plugin_errors_total" in body  # 验证插件错误计数存在
    settings.PROMETHEUS_ENABLED = original_flag  # 恢复原始配置
    importlib.reload(importlib.import_module("app.telemetry.metrics"))  # 恢复指标模块状态
