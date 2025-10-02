"""VPS 生命周期管理占位模块。

说明真实实现应如何与云厂商 API 对接，并强调最小权限策略。
"""

from __future__ import annotations

import structlog  # 输出结构化日志

LOGGER = structlog.get_logger()  # 初始化日志器


def create_vps_instance(provider: str, region: str) -> None:
    """创建 VPS 实例的占位函数。

    推荐流程：
    1. 在密钥管理服务中创建具备最小权限的 API Key；
    2. 使用官方 SDK（如 boto3、alibabacloud Tea）构造创建请求；
    3. 将实例 ID、IP 等元数据写入配置中心或数据库；
    4. 捕获网络异常并实现重试退避策略。
    """

    LOGGER.info("vps_create_placeholder", provider=provider, region=region)
    raise NotImplementedError("VPS 创建逻辑待实现")


def destroy_vps_instance(instance_id: str) -> None:
    """销毁 VPS 实例的占位函数。

    实际逻辑应在删除前做数据备份与告警，并确认实例已不再被任务使用。
    """

    LOGGER.info("vps_destroy_placeholder", instance_id=instance_id)
    raise NotImplementedError("VPS 销毁逻辑待实现")
