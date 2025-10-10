"""调度包初始化，导出核心函数供外部调用。"""  # 模块说明

from __future__ import annotations  # 启用未来注解语法

from .service import run_profile, start_scheduler  # 导入核心函数

__all__ = ["run_profile", "start_scheduler"]  # 明确导出的接口
