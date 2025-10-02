"""VPS 生命周期管理占位模块。"""

from __future__ import annotations  # 启用未来注解


def create_instance() -> None:
    """创建 VPS 实例的占位函数。"""

    # TODO: 在此调用云厂商 API（例如 AWS、阿里云、GCP）创建临时实例
    # 建议接入临时凭据与安全组最小权限策略
    raise NotImplementedError("请在生产环境中实现云厂商 API 调用")


def destroy_instance() -> None:
    """销毁 VPS 实例的占位函数。"""

    # TODO: 在此调用云厂商 API 释放实例资源
    # 需确保删除磁盘快照与密钥文件，避免残留敏感信息
    raise NotImplementedError("请在生产环境中实现实例销毁逻辑")
