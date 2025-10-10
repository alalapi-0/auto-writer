# -*- coding: utf-8 -*-  # 指定 UTF-8 编码防止中文注释乱码
"""封装通用后台线程，负责运行长耗时任务并通过信号返回日志。"""  # 模块用途描述

from __future__ import annotations  # 启用未来注解语法提升类型提示灵活度

import traceback  # 捕获异常堆栈以便记录
from typing import Any, Callable, Iterable  # 引入泛型类型与可迭代对象

from PySide6.QtCore import QThread, Signal  # Qt 线程与信号基类

from app.utils.logger import get_logger  # 引入统一日志模块

LOGGER = get_logger(__name__)  # 初始化模块级记录器


class TaskWorker(QThread):  # 通用后台线程实现
    """包装任意可迭代任务并通过信号输出日志。"""  # 类说明

    log_signal = Signal(str)  # 日志信号用于输出每一行文本
    done_signal = Signal(int)  # 完成信号携带返回码 0=成功 1=失败

    def __init__(self, func: Callable[..., Iterable[str] | None], *args: Any, **kwargs: Any) -> None:  # 构造函数记录待执行任务
        super().__init__()  # 初始化 QThread 基类
        self.func = func  # 保存任务函数引用
        self.args = args  # 保存位置参数
        self.kwargs = kwargs  # 保存关键字参数

    def run(self) -> None:  # 线程启动后的执行入口
        try:
            result = self.func(*self.args, **self.kwargs)  # 执行外部传入的任务函数
            if result is not None:  # 若返回可迭代对象
                for line in result:  # 逐行遍历日志输出
                    if self.isInterruptionRequested():  # 若收到中断请求
                        LOGGER.debug("任务被请求中断，提前退出")  # 记录调试日志
                        break  # 跳出循环
                    if line is None:  # 忽略空行
                        continue  # 直接跳过
                    self.log_signal.emit(str(line))  # 通过信号发送日志文本
            self.done_signal.emit(0)  # 正常完成发出成功信号
        except Exception as exc:  # noqa: BLE001  # 捕获任意异常保持线程稳定
            stack = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))  # 格式化堆栈
            LOGGER.error("后台线程异常\n%s", stack)  # 写入错误日志
            self.log_signal.emit(f"[ERROR] {exc}")  # 通知界面出现错误
            self.done_signal.emit(1)  # 通知界面任务失败

    def stop(self) -> None:  # 供外部调用的停止方法
        self.requestInterruption()  # 设置中断标记
        self.quit()  # 请求线程优雅退出
        self.wait(2000)  # 最多等待 2 秒结束
