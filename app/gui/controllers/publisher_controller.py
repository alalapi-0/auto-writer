# -*- coding: utf-8 -*-  # 指定 UTF-8 编码
"""负责批量投递草稿与导出报表。"""  # 模块说明

from __future__ import annotations  # 启用未来注解

import subprocess  # 启动外部脚本
import sys  # 获取解释器路径
from pathlib import Path  # 构造脚本路径
from typing import Callable, Optional  # 类型提示

from PySide6.QtWidgets import QMessageBox  # 弹窗提示

from app.gui.controllers.task_worker import TaskWorker  # 通用后台线程
from app.gui.widgets.report_viewer import ReportViewer  # 报表组件类型提示
from app.observability.report import generate_report  # 直接调用报表生成逻辑
from app.utils.logger import get_logger  # 日志模块

LOGGER = get_logger(__name__)  # 初始化控制器日志器


class PublisherController:  # 投递控制器
    """通过后台线程执行 publish_all 并更新界面。"""  # 类说明

    def __init__(
        self,
        log_callback: Callable[[str], None],
        status_callback: Callable[[str, str], None],
        report_viewer: ReportViewer,
    ) -> None:  # 构造函数
        self.log_callback = log_callback  # 保存日志回调
        self.status_callback = status_callback  # 保存状态回调
        self.report_viewer = report_viewer  # 保存报表组件引用
        self.logger = LOGGER  # 暴露日志器
        self.worker: Optional[TaskWorker] = None  # 记录当前线程
        self._current_process: Optional[subprocess.Popen[str]] = None  # 子进程引用

    def start_publish(self) -> None:  # 启动批量投递
        if self.worker and self.worker.isRunning():  # 检查是否已有任务
            QMessageBox.warning(None, "任务进行中", "草稿投递正在执行，请稍候")  # 提示用户
            return  # 直接返回
        self.status_callback("#4c8bf5", "草稿投递中……")  # 更新状态灯
        self.logger.info("准备启动批量投递")  # 输出日志
        self.worker = TaskWorker(self._run_publish)  # 创建后台线程
        self.worker.log_signal.connect(self.log_callback)  # 连接日志信号
        self.worker.done_signal.connect(self._on_finished)  # 连接完成信号
        self.worker.start()  # 启动线程

    def _run_publish(self):  # 线程实际执行逻辑
        script_path = Path("scripts/publish_all.py")  # 定义脚本路径
        if not script_path.exists():  # 若脚本不存在
            raise FileNotFoundError("未找到 publish_all.py 脚本")  # 抛出异常
        yield f"[INFO] 即将执行 {script_path}"  # 输出准备日志
        command = [sys.executable, str(script_path)]  # 构造命令
        self.logger.debug("执行命令=%s", command)  # 记录调试信息
        self._current_process = subprocess.Popen(  # 启动脚本
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        assert self._current_process.stdout is not None  # 确保 stdout 可读
        for line in self._current_process.stdout:  # 逐行读取输出
            yield line.rstrip()  # 返回日志文本
        code = self._current_process.wait()  # 等待结束
        if code != 0:  # 判断状态
            raise RuntimeError(f"publish_all 退出码 {code}")  # 抛出异常
        yield "[INFO] 草稿投递完成"  # 输出完成日志

    def _on_finished(self, code: int) -> None:  # 完成信号回调
        self._current_process = None  # 清理进程
        if code == 0:  # 成功
            self.status_callback("#1abc9c", "投递完成")  # 更新状态灯
            QMessageBox.information(None, "投递完成", "草稿已经成功投递")  # 弹窗提示
            self.export_report()  # 自动刷新报表
        else:  # 失败
            self.status_callback("#e74c3c", "投递失败")  # 更新状态灯
            QMessageBox.critical(None, "投递失败", "投递过程中出现错误，请查看日志")  # 弹窗提示

    def export_report(self) -> None:  # 导出报表并更新界面
        self.logger.info("开始导出报表")  # 记录日志
        result = generate_report(window_days=7)  # 调用报表生成
        self.report_viewer.update_report(result["data"])  # 更新报表组件
        self.log_callback(f"[INFO] 报表已导出: {result['json']}")  # 将路径写入日志

    def shutdown(self) -> None:  # 清理资源
        if self.worker and self.worker.isRunning():  # 若线程仍在运行
            self.logger.info("尝试停止投递线程")  # 输出日志
            self.worker.stop()  # 请求线程停止
        if self._current_process and self._current_process.poll() is None:  # 若进程仍存活
            self.logger.warning("尝试终止投递子进程")  # 输出警告
            self._current_process.terminate()  # 终止
            self._current_process = None  # 清理引用
