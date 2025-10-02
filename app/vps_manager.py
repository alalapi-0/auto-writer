"""VPS 生命周期管理占位模块。"""

from __future__ import annotations

import structlog

LOGGER = structlog.get_logger()


def create_vps_instance(provider: str, region: str) -> None:
    """创建 VPS 实例的占位函数。"""

    # 真实实现应调用云厂商 API，例如 AWS、阿里云或腾讯云。
    # 需要在此位置构造 API 请求，处理鉴权，并记录实例 ID。
    LOGGER.info("vps_create_placeholder", provider=provider, region=region)
    raise NotImplementedError("VPS 创建逻辑待实现")


def destroy_vps_instance(instance_id: str) -> None:
    """销毁 VPS 实例的占位函数。"""

    # 真实实现需调用云厂商提供的删除接口，确保资源释放。
    LOGGER.info("vps_destroy_placeholder", instance_id=instance_id)
    raise NotImplementedError("VPS 销毁逻辑待实现")
