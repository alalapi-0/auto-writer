# -*- coding: utf-8 -*-  # 指定 UTF-8 编码
"""系统监控控制器，负责执行 doctor 并更新状态面板。"""  # 模块说明

from __future__ import annotations  # 启用未来注解

import subprocess  # 运行自检脚本
import sys  # 获取解释器路径
from dataclasses import dataclass  # 定义结构体
from typing import Callable, List, Optional  # 类型提示

from app.gui.controllers.task_worker import TaskWorker  # 通用后台线程
from app.gui.widgets.status_panel import StatusPanel, SimpleCheck  # 状态面板类型
from app.utils.logger import get_logger  # 日志模块

LOGGER = get_logger(__name__)  # 初始化日志器


@dataclass
class CheckResult:  # 简化后的检查结果结构
    name: str  # 检查项名称
    status: str  # 状态图标
    message: str  # 详细说明


class MonitorController:  # 系统监控控制器
    """定期运行 doctor 并解析输出。"""  # 类说明

    def __init__(self, log_callback: Callable[[str], None], status_panel: StatusPanel) -> None:  # 构造函数
        self.log_callback = log_callback  # 保存日志回调
        self.status_panel = status_panel  # 保存状态面板
        self.logger = LOGGER  # 暴露日志器
        self.worker: Optional[TaskWorker] = None  # 后台线程引用
        self._current_process: Optional[subprocess.Popen[str]] = None  # 子进程引用
        self._latest_checks: List[CheckResult] = []  # 最近一次检查结果

    def refresh_status(self) -> None:  # 启动 doctor 检查
        if self.worker and self.worker.isRunning():  # 避免并发运行
            self.logger.debug("自检仍在运行，跳过本次刷新")  # 输出调试日志
            return  # 直接返回
        self.logger.info("开始执行系统自检")  # 记录日志
        self.worker = TaskWorker(self._run_doctor)  # 创建线程
        self.worker.log_signal.connect(self.log_callback)  # 连接日志信号
        self.worker.done_signal.connect(self._on_finished)  # 连接完成信号
        self.worker.start()  # 启动线程

    def _run_doctor(self):  # 在线程中执行 doctor
        self._latest_checks = []  # 清空旧结果
        command = [sys.executable, "-m", "scripts.doctor"]  # 构造命令
        self._current_process = subprocess.Popen(  # 启动进程
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        assert self._current_process.stdout is not None  # 确保 stdout 可读
        for line in self._current_process.stdout:  # 逐行读取输出
            text = line.rstrip()  # 去除换行
            if text:  # 非空行写入日志
                self._parse_line(text)  # 尝试解析检查结果
            yield text  # 返回给日志窗口
        code = self._current_process.wait()  # 等待结束
        if code != 0:  # 若退出码非零
            raise RuntimeError(f"doctor 退出码 {code}")  # 抛出异常
        yield "[INFO] 自检完成"  # 输出完成日志

    def _parse_line(self, line: str) -> None:  # 解析 doctor 输出
        if not line or line[0] not in {"✅", "⚠️", "❌"}:  # 判断是否符合格式
            return  # 非检查结果行直接跳过
        try:
            symbol, rest = line.split(" ", 1)  # 拆分状态符号与剩余文本
            name, message = rest.split(":", 1)  # 根据冒号拆分名称与消息
            self._latest_checks.append(CheckResult(name=name.strip(), status=symbol, message=message.strip()))  # 保存结果
        except ValueError:  # 拆分失败时
            self.logger.debug("无法解析自检行: %s", line)  # 输出调试

    def _on_finished(self, code: int) -> None:  # 线程完成回调
        self._current_process = None  # 清理子进程
        if code == 0:  # 成功时
            simple = [SimpleCheck(name=item.name, status=item.status, message=item.message) for item in self._latest_checks]  # 转换为简单结构
            self.status_panel.update_checks(simple)  # 更新状态面板
        else:  # 失败时
            self.status_panel.update_error("doctor 执行失败，请检查日志")  # 显示错误

    def shutdown(self) -> None:  # 清理资源
        if self.worker and self.worker.isRunning():  # 若线程仍运行
            self.logger.info("尝试停止自检线程")  # 输出日志
            self.worker.stop()  # 请求停止
        if self._current_process and self._current_process.poll() is None:  # 若子进程仍存活
            self.logger.warning("尝试终止自检进程")  # 输出警告
            self._current_process.terminate()  # 终止进程
            self._current_process = None  # 清理引用
