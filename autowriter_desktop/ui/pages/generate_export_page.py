"""生成与导出页面实现。"""
from __future__ import annotations

from pathlib import Path
from typing import Callable

from PySide6.QtCore import QDate, QThread
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QDateEdit,
    QSpinBox,
    QMessageBox,
)

from ...core import runner
from ...core.signals import TaskSignals
from ..widgets.progress_console import ProgressConsole
from ..widgets.table_index import TableIndexWidget


class SingleTaskThread(QThread):
    """封装单个 CLI 调用线程。"""

    def __init__(self, task_callable: Callable[[], tuple[int, Path]]):
        super().__init__()
        self.task_callable = task_callable
        self.signals = TaskSignals()

    def run(self) -> None:  # type: ignore[override]
        try:
            code, path = self.task_callable()
            self.signals.progress.emit(f"任务结束，返回码 {code}，输出 {path}")
            self.signals.finished.emit(code)
        except Exception as exc:  # noqa: BLE001
            self.signals.error.emit(str(exc))
            self.signals.finished.emit(1)


class GenerateExportPage(QWidget):
    """生成与导出功能页。"""

    def __init__(self, main_window) -> None:
        super().__init__(main_window)
        self.main_window = main_window
        self.console = ProgressConsole(self)
        self.index_table = TableIndexWidget(self)
        self.date_edit = QDateEdit(self)
        self.count_spin = QSpinBox(self)
        self.generate_button = QPushButton("生成内容", self)
        self.export_wechat_button = QPushButton("导出微信", self)
        self.export_zhihu_button = QPushButton("导出知乎", self)
        self.export_all_button = QPushButton("导出全部", self)
        self.refresh_index_button = QPushButton("刷新索引", self)
        self._current_thread: SingleTaskThread | None = None
        self._last_platform = "all"
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        form_row = QHBoxLayout()
        form_row.addWidget(QLabel("日期:", self))
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setDisplayFormat("yyyy-MM-dd")
        self.date_edit.setDate(QDate.currentDate())
        form_row.addWidget(self.date_edit)
        form_row.addWidget(QLabel("生成条数:", self))
        self.count_spin.setRange(1, 50)
        self.count_spin.setValue(int(self.main_window.config.get("default_count", 5)))
        form_row.addWidget(self.count_spin)
        form_row.addStretch(1)
        layout.addLayout(form_row)

        button_row = QHBoxLayout()
        button_row.addWidget(self.generate_button)
        button_row.addWidget(self.export_wechat_button)
        button_row.addWidget(self.export_zhihu_button)
        button_row.addWidget(self.export_all_button)
        button_row.addWidget(self.refresh_index_button)
        button_row.addStretch(1)
        layout.addLayout(button_row)

        layout.addWidget(self.console)
        layout.addWidget(self.index_table)

        self.generate_button.clicked.connect(self.start_generate)
        self.export_wechat_button.clicked.connect(lambda: self.start_export("wechat"))
        self.export_zhihu_button.clicked.connect(lambda: self.start_export("zhihu"))
        self.export_all_button.clicked.connect(lambda: self.start_export("all"))
        self.refresh_index_button.clicked.connect(self.refresh_index)

    def _ensure_idle(self) -> bool:
        if self._current_thread and self._current_thread.isRunning():
            QMessageBox.warning(self, "AutoWriter", "任务执行中，请稍候")
            return False
        return True

    def start_generate(self) -> None:
        if not self._ensure_idle():
            return
        self.console.clear()
        count = self.count_spin.value()
        self._run_task(lambda: runner.run_generate(count, self.console.append_line))
        self._last_platform = "all"

    def start_export(self, platform: str) -> None:
        if not self._ensure_idle():
            return
        self.console.clear()
        date = self.date_edit.date().toString("yyyy-MM-dd")
        self._run_task(lambda: runner.run_export(platform, date, self.console.append_line))
        self._last_platform = platform

    def refresh_index(self) -> None:
        date = self.date_edit.date().toString("yyyy-MM-dd")
        platform = self._last_platform
        self.index_table.load_index(platform, date)

    def _run_task(self, callable_obj) -> None:
        thread = SingleTaskThread(callable_obj)
        thread.signals.progress.connect(self.console.append_line)
        thread.signals.error.connect(lambda msg: QMessageBox.critical(self, "AutoWriter", msg))
        thread.signals.finished.connect(self._on_task_finished)
        self._current_thread = thread
        thread.start()

    def _on_task_finished(self, code: int) -> None:
        if code == 0:
            self.console.append_line("任务成功完成")
        else:
            self.console.append_line(f"任务返回码：{code}")
        self.refresh_index()

    def on_page_activated(self) -> None:
        # 每次进入页面时同步最新配置
        self.count_spin.setValue(int(self.main_window.config.get("default_count", 5)))
        self.refresh_index()
