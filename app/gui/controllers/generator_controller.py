# -*- coding: utf-8 -*-  # 指定 UTF-8 编码避免中文注释乱码
"""负责触发文章生成流程并将日志输出到 GUI。"""  # 模块说明

from __future__ import annotations  # 启用未来注解

import subprocess  # 运行外部脚本
import sys  # 获取 Python 解释器路径
from pathlib import Path  # 构建脚本绝对路径
from typing import Callable, Optional  # 类型注解

from PySide6.QtWidgets import QMessageBox  # 用于提示任务结果

from app.gui.controllers.task_worker import TaskWorker  # 导入通用后台线程
from app.utils.logger import get_logger  # 引入统一日志模块

LOGGER = get_logger(__name__)  # 初始化控制器日志器


class GeneratorController:  # 定义生成控制器
    """负责在后台线程中执行文章生成脚本。"""  # 类说明

    def __init__(self, log_callback: Callable[[str], None], status_callback: Callable[[str, str], None]) -> None:  # 构造函数
        self.log_callback = log_callback  # 保存日志回调
        self.status_callback = status_callback  # 保存状态灯回调
        self.logger = LOGGER  # 暴露日志器供主窗口附加 handler
        self.worker: Optional[TaskWorker] = None  # 记录当前线程
        self._current_process: Optional[subprocess.Popen[str]] = None  # 保存子进程引用便于停止

    def start_generation(self) -> None:  # 启动生成任务
        if self.worker and self.worker.isRunning():  # 若已有任务运行
            QMessageBox.warning(None, "任务进行中", "文章生成正在进行，请稍后再试")  # 提示用户
            return  # 直接返回
        self.status_callback("#4c8bf5", "生成文章中……")  # 更新状态灯为运行中
        self.logger.info("准备启动文章生成流程")  # 输出日志
        self.worker = TaskWorker(self._run_generation)  # 创建后台线程
        self.worker.log_signal.connect(self.log_callback)  # 连接日志信号
        self.worker.done_signal.connect(self._on_finished)  # 连接完成信号
        self.worker.start()  # 启动线程

    def _run_generation(self):  # 在线程内执行的函数，返回迭代器
        script_candidates = [  # 备选脚本路径
            Path("scripts/generate_articles.py"),  # Round 5 规范脚本
            Path("app/orchestrator/orchestrator.py"),  # Orchestrator 主脚本
            Path("app/main.py"),  # 旧版主入口
        ]
        target = next((path for path in script_candidates if path.exists()), None)  # 选择存在的脚本
        if target is None:  # 若没有匹配脚本
            raise FileNotFoundError("未找到可用的文章生成脚本")  # 抛出异常
        yield f"[INFO] 即将执行 {target}"  # 输出准备日志
        command = [sys.executable, str(target)]  # 构造命令
        self.logger.debug("执行命令=%s", command)  # 记录调试信息
        self._current_process = subprocess.Popen(  # 启动子进程
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        assert self._current_process.stdout is not None  # 静态检查：stdout 必不为空
        for line in self._current_process.stdout:  # 逐行读取输出
            yield line.rstrip()  # 去除换行并返回
        return_code = self._current_process.wait()  # 等待进程结束
        if return_code != 0:  # 判断是否成功
            raise RuntimeError(f"文章生成脚本退出码 {return_code}")  # 报错
        yield "[INFO] 文章生成完成"  # 提示成功

    def _on_finished(self, code: int) -> None:  # 线程结束回调
        self._current_process = None  # 清理子进程引用
        if code == 0:  # 成功时
            self.status_callback("#1abc9c", "生成完成")  # 状态灯转为绿色
            QMessageBox.information(None, "生成完成", "文章已经成功生成")  # 弹窗提示
        else:  # 失败时
            self.status_callback("#e74c3c", "生成失败")  # 状态灯转为红色
            QMessageBox.critical(None, "生成失败", "生成过程中出现错误，请查看日志")  # 弹窗提示

    def shutdown(self) -> None:  # 程序关闭时清理资源
        if self.worker and self.worker.isRunning():  # 如果线程仍在运行
            self.logger.info("正在尝试停止文章生成线程")  # 输出日志
            self.worker.stop()  # 请求线程停止
        if self._current_process and self._current_process.poll() is None:  # 若子进程存在
            self.logger.warning("正在终止文章生成子进程")  # 输出警告
            self._current_process.terminate()  # 发送终止信号
            self._current_process = None  # 清理引用
