"""定义平台投递的统一返回结构与状态枚举。"""  # 模块中文说明
from __future__ import annotations  # 启用未来注解语法
from dataclasses import dataclass  # 引入 dataclass 装饰器
from typing import Optional, Dict, Any, Literal  # 导入类型提示

DeliveryStatus = Literal["skipped", "prepared", "queued", "success", "failed"]  # 声明统一状态取值


@dataclass(slots=True)  # 使用 slots 减少内存占用
class DeliveryResult:
    """平台适配器统一返回值结构。"""  # 类中文文档

    platform: str  # 平台名称
    status: DeliveryStatus  # 统一状态字段
    target_id: Optional[str] = None  # 平台草稿/稿件 ID
    out_dir: Optional[str] = None  # 本地输出目录
    payload: Optional[Dict[str, Any]] = None  # 用于审计或重试的材料
    error: Optional[str] = None  # 错误描述
