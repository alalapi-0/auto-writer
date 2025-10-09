"""平台适配器注册表，根据配置动态加载。"""  # 模块中文说明
from __future__ import annotations  # 启用未来注解语法
from typing import Dict, Callable  # 导入类型提示

from app.delivery.types import DeliveryResult  # 引入统一返回类型

Adapter = Callable[[dict, object], DeliveryResult]  # 定义适配器签名


def get_registry(settings) -> Dict[str, Adapter]:
    """根据配置返回启用的平台适配器映射。"""  # 函数中文文档

    registry: Dict[str, Adapter] = {}  # 初始化注册表
    from app.delivery.wechat_mp_adapter import deliver as wx  # 延迟导入公众号适配器
    from app.delivery.zhihu_adapter import deliver as zh  # 延迟导入知乎适配器
    if "wechat_mp" in getattr(settings, "delivery_enabled_platforms", []):  # 判断是否启用公众号
        registry["wechat_mp"] = wx  # 注册公众号适配器
    if "zhihu" in getattr(settings, "delivery_enabled_platforms", []):  # 判断是否启用知乎
        registry["zhihu"] = zh  # 注册知乎适配器
    return registry  # 返回注册表
