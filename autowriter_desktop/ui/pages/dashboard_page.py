"""仪表盘页面。"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Callable, List, Tuple

from PySide6.QtCore import QThread
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QLabel,
    QPushButton,
    QHBoxLayout,
    QMessageBox,
    QGroupBox,
)

from ...core import runner, paths
from ...core.signals import TaskSignals
from ..widgets.progress_console import ProgressConsole


class WorkflowThread(QThread):
    """串行执行多个任务的线程。"""

    def __init__(self, steps: List[Callable[[], Tuple[int, Path]]], continue_on_error: bool) -> None:
        super().__init__()
        self.steps = steps
        self.continue_on_error = continue_on_error
        self.signals = TaskSignals()

    def run(self) -> None:  # type: ignore[override]
        exit_code = 0
        try:
            for index, step in enumerate(self.steps, start=1):
                code, result_path = step()
                self.signals.progress.emit(f"步骤 {index} 完成，返回码 {code}，输出目录 {result_path}")
                if code != 0 and not self.continue_on_error:
                    exit_code = code
                    break
        except Exception as exc:  # noqa: BLE001
            self.signals.error.emit(str(exc))
            exit_code = 1
        self.signals.finished.emit(exit_code)


class DashboardPage(QWidget):
    """展示统计数据与快捷按钮的仪表盘。"""

    def __init__(self, main_window) -> None:
        super().__init__(main_window)
        self.main_window = main_window
        self.console = ProgressConsole(self)
        self.stats_label = QLabel(self)
        self.summary_label = QLabel(self)
        self.full_flow_button = QPushButton("今天全流程", self)
        self.auto_only_button = QPushButton("仅送草稿", self)
        self.cancel_button = QPushButton("取消当前任务", self)
        self._current_thread: WorkflowThread | None = None
        self._build_ui()
        self.refresh_summary()

    def _build_ui(self) -> None:
        """搭建界面布局。"""
        layout = QVBoxLayout(self)
        layout.addWidget(self._build_stats_box())

        button_row = QHBoxLayout()
        button_row.addWidget(self.full_flow_button)
        button_row.addWidget(self.auto_only_button)
        button_row.addWidget(self.cancel_button)
        button_row.addStretch(1)
        layout.addLayout(button_row)

        layout.addWidget(self.console)

        self.full_flow_button.clicked.connect(self.start_full_flow)
        self.auto_only_button.clicked.connect(self.start_auto_only)
        self.cancel_button.clicked.connect(runner.cancel_current_process)

    def _build_stats_box(self) -> QGroupBox:
        box = QGroupBox("今日概览", self)
        box_layout = QVBoxLayout(box)
        self.stats_label.setWordWrap(True)
        self.summary_label.setWordWrap(True)
        box_layout.addWidget(self.stats_label)
        box_layout.addWidget(self.summary_label)
        return box

    def refresh_summary(self) -> None:
        """读取导出数量和自动送草稿摘要。"""
        today = datetime.now().strftime("%Y-%m-%d")
        exports_dir = paths.get_export_root()
        total_articles = 0
        if exports_dir.exists():
            for platform_dir in exports_dir.iterdir():
                day_dir = platform_dir / today
                csv_file = day_dir / "index.csv"
                if csv_file.exists():
                    # 逐行统计 index.csv，减去表头即为文章数量
                    with csv_file.open("r", encoding="utf-8") as fh:
                        lines = sum(1 for _ in fh) - 1
                        total_articles += max(lines, 0)
        self.stats_label.setText(f"今日生成内容条数预估：{total_articles}")

        summary_path = paths.automation_log_dir(today) / "summary.json"
        if summary_path.exists():
            with summary_path.open("r", encoding="utf-8") as fh:
                data = json.load(fh)
            success = len(data.get("success", []))
            failed = len(data.get("failed", []))
            skipped = len(data.get("skipped", []))
            self.summary_label.setText(
                f"送草稿结果：成功 {success}，失败 {failed}，跳过 {skipped}"
            )
        else:
            self.summary_label.setText("暂无送草稿记录")

    def start_full_flow(self) -> None:
        """一键执行全流程。"""
        if self._current_thread and self._current_thread.isRunning():
            QMessageBox.warning(self, "AutoWriter", "任务执行中，请先等待完成")
            return
        self.console.clear()
        config = self.main_window.config
        today = datetime.now().strftime("%Y-%m-%d")
        # 组合顺序执行的步骤：生成 -> 导出 -> 自动送草稿
        steps = [
            lambda: runner.run_generate(config.get("default_count", 5), self.console.append_line),
            lambda: runner.run_export("all", today, self.console.append_line),
            lambda: runner.run_auto(
                "all",
                today,
                config.get("cdp_port", 9222),
                self.console.append_line,
                max_retries=config.get("retry_max"),
                min_interval=config.get("min_interval"),
                max_interval=config.get("max_interval"),
            ),
        ]
        self._start_thread(steps, bool(config.get("continue_on_error")))

    def start_auto_only(self) -> None:
        """仅执行送草稿。"""
        if self._current_thread and self._current_thread.isRunning():
            QMessageBox.warning(self, "AutoWriter", "任务执行中，请先等待完成")
            return
        self.console.clear()
        config = self.main_window.config
        today = datetime.now().strftime("%Y-%m-%d")
        # 仅执行送草稿
        steps = [
            lambda: runner.run_auto(
                "all",
                today,
                config.get("cdp_port", 9222),
                self.console.append_line,
                max_retries=config.get("retry_max"),
                min_interval=config.get("min_interval"),
                max_interval=config.get("max_interval"),
            )
        ]
        self._start_thread(steps, True)

    def _start_thread(self, steps: List[Callable[[], Tuple[int, Path]]], continue_on_error: bool) -> None:
        self.full_flow_button.setEnabled(False)
        self.auto_only_button.setEnabled(False)
        thread = WorkflowThread(steps, continue_on_error)
        thread.signals.progress.connect(self.console.append_line)
        thread.signals.error.connect(lambda msg: QMessageBox.critical(self, "AutoWriter", msg))
        thread.signals.finished.connect(self._on_thread_finished)
        self._current_thread = thread
        thread.start()

    def _on_thread_finished(self, code: int) -> None:
        self.full_flow_button.setEnabled(True)
        self.auto_only_button.setEnabled(True)
        if code == 0:
            self.console.append_line("任务完成")
        else:
            self.console.append_line(f"任务以返回码 {code} 结束")
        self.refresh_summary()

    def on_page_activated(self) -> None:
        """页面切换时刷新。"""
        self.refresh_summary()
