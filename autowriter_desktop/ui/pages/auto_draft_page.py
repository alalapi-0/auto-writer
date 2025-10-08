"""自动送草稿页面。"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Callable

import httpx
from PySide6.QtCore import QDate, QThread
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QDateEdit,
    QSpinBox,
    QComboBox,
    QCheckBox,
    QMessageBox,
    QTableWidget,
    QTableWidgetItem,
)

from ...core import runner, paths
from ...core.signals import TaskSignals
from ..widgets.progress_console import ProgressConsole
from ..widgets.table_index import open_path_in_explorer


class AutoTaskThread(QThread):
    """后台线程执行送草稿。"""

    def __init__(self, task_callable: Callable[[], tuple[int, Path]]):
        super().__init__()
        self.task_callable = task_callable
        self.signals = TaskSignals()

    def run(self) -> None:  # type: ignore[override]
        try:
            code, path = self.task_callable()
            self.signals.progress.emit(f"任务完成，返回码 {code}，日志目录 {path}")
            self.signals.finished.emit(code)
        except Exception as exc:  # noqa: BLE001
            self.signals.error.emit(str(exc))
            self.signals.finished.emit(1)


class AutoDraftPage(QWidget):
    """自动送草稿功能页。"""

    def __init__(self, main_window) -> None:
        super().__init__(main_window)
        self.main_window = main_window
        self.console = ProgressConsole(self)
        self.summary_table = QTableWidget(self)
        self.date_edit = QDateEdit(self)
        self.platform_combo = QComboBox(self)
        self.port_spin = QSpinBox(self)
        self.dry_run_check = QCheckBox("Dry Run (不提交)", self)
        self.retry_spin = QSpinBox(self)
        self.min_interval_spin = QSpinBox(self)
        self.max_interval_spin = QSpinBox(self)
        self.test_button = QPushButton("测试连接", self)
        self.start_button = QPushButton("开始送草稿", self)
        self.cancel_button = QPushButton("取消", self)
        self.open_log_button = QPushButton("打开日志目录", self)
        self.log_path_label = QLabel(self)
        self._current_thread: AutoTaskThread | None = None
        self._setup_ui()
        self.load_summary()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        form_row = QHBoxLayout()
        form_row.addWidget(QLabel("日期:", self))
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setDisplayFormat("yyyy-MM-dd")
        self.date_edit.setDate(QDate.currentDate())
        form_row.addWidget(self.date_edit)

        form_row.addWidget(QLabel("平台:", self))
        self.platform_combo.addItems(["wechat", "zhihu", "all"])
        form_row.addWidget(self.platform_combo)

        form_row.addWidget(QLabel("CDP 端口:", self))
        self.port_spin.setRange(1000, 65535)
        self.port_spin.setValue(int(self.main_window.config.get("cdp_port", 9222)))
        form_row.addWidget(self.port_spin)
        layout.addLayout(form_row)

        advanced_row = QHBoxLayout()
        advanced_row.addWidget(QLabel("最大重试:", self))
        self.retry_spin.setRange(0, 10)
        self.retry_spin.setValue(int(self.main_window.config.get("retry_max", 3)))
        advanced_row.addWidget(self.retry_spin)

        advanced_row.addWidget(QLabel("最小间隔(秒):", self))
        self.min_interval_spin.setRange(0, 60)
        self.min_interval_spin.setValue(int(self.main_window.config.get("min_interval", 3)))
        advanced_row.addWidget(self.min_interval_spin)

        advanced_row.addWidget(QLabel("最大间隔(秒):", self))
        self.max_interval_spin.setRange(0, 120)
        self.max_interval_spin.setValue(int(self.main_window.config.get("max_interval", 6)))
        advanced_row.addWidget(self.max_interval_spin)

        advanced_row.addWidget(self.dry_run_check)
        advanced_row.addStretch(1)
        layout.addLayout(advanced_row)

        button_row = QHBoxLayout()
        button_row.addWidget(self.test_button)
        button_row.addWidget(self.start_button)
        button_row.addWidget(self.cancel_button)
        button_row.addWidget(self.open_log_button)
        button_row.addStretch(1)
        layout.addLayout(button_row)

        layout.addWidget(self.log_path_label)
        layout.addWidget(self.console)
        layout.addWidget(self.summary_table)

        self.summary_table.setColumnCount(3)
        self.summary_table.setHorizontalHeaderLabels(["状态", "标题", "备注"])
        self.summary_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.summary_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.summary_table.setSelectionMode(QTableWidget.SingleSelection)

        self.test_button.clicked.connect(self.test_connection)
        self.start_button.clicked.connect(self.start_task)
        self.cancel_button.clicked.connect(runner.cancel_current_process)
        self.open_log_button.clicked.connect(self.open_logs)
        self.date_edit.dateChanged.connect(lambda *_: self.load_summary())

    def _ensure_idle(self) -> bool:
        if self._current_thread and self._current_thread.isRunning():
            QMessageBox.warning(self, "AutoWriter", "任务执行中，请稍候")
            return False
        return True

    def test_connection(self) -> None:
        port = self.port_spin.value()
        url = f"http://127.0.0.1:{port}/json/version"
        try:
            # 使用 httpx 直接探测 CDP 接口是否可用
            response = httpx.get(url, timeout=3.0)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            QMessageBox.critical(
                self,
                "AutoWriter",
                f"连接失败：{exc}\n请确保浏览器以 --remote-debugging-port={port} 启动。",
            )
            return
        data = response.json()
        version = data.get("Browser", "未知版本")
        QMessageBox.information(self, "AutoWriter", f"连接成功：{version}")

    def start_task(self) -> None:
        if not self._ensure_idle():
            return
        self.console.clear()
        date = self.date_edit.date().toString("yyyy-MM-dd")
        platform = self.platform_combo.currentText()
        port = self.port_spin.value()
        dry_run = self.dry_run_check.isChecked()
        max_retries = self.retry_spin.value()
        min_interval = self.min_interval_spin.value()
        max_interval = self.max_interval_spin.value()

        def task():
            return runner.run_auto(
                platform,
                date,
                port,
                self.console.append_line,
                dry_run=dry_run,
                max_retries=max_retries,
                min_interval=min_interval,
                max_interval=max_interval,
            )

        thread = AutoTaskThread(task)
        thread.signals.progress.connect(self.console.append_line)
        thread.signals.error.connect(lambda msg: QMessageBox.critical(self, "AutoWriter", msg))
        thread.signals.finished.connect(self._on_task_finished)
        self._current_thread = thread
        thread.start()

    def _on_task_finished(self, code: int) -> None:
        if code == 0:
            self.console.append_line("任务完成")
        else:
            self.console.append_line(f"任务返回码 {code}")
        self.load_summary()

    def load_summary(self) -> None:
        date = self.date_edit.date().toString("yyyy-MM-dd")
        summary_path = paths.automation_log_dir(date) / "summary.json"
        self.log_path_label.setText(f"日志目录：{summary_path.parent}")
        if not summary_path.exists():
            self.summary_table.setRowCount(0)
            return
        with summary_path.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
        rows: list[tuple[str, str, str]] = []
        for status in ("success", "failed", "skipped"):
            for item in data.get(status, []):
                title = item.get("title") or item.get("name") or "-"
                message = item.get("message") or item.get("reason") or ""
                rows.append((status, title, message))
        self.summary_table.setRowCount(len(rows))
        for row_index, (status, title, message) in enumerate(rows):
            self.summary_table.setItem(row_index, 0, QTableWidgetItem(status))
            self.summary_table.setItem(row_index, 1, QTableWidgetItem(title))
            self.summary_table.setItem(row_index, 2, QTableWidgetItem(message))
        self.summary_table.resizeColumnsToContents()

    def open_logs(self) -> None:
        date = self.date_edit.date().toString("yyyy-MM-dd")
        log_dir = paths.automation_log_dir(date)
        log_dir.mkdir(parents=True, exist_ok=True)
        open_path_in_explorer(log_dir)

    def on_page_activated(self) -> None:
        cfg = self.main_window.config
        self.port_spin.setValue(int(cfg.get("cdp_port", 9222)))
        self.retry_spin.setValue(int(cfg.get("retry_max", 3)))
        self.min_interval_spin.setValue(int(cfg.get("min_interval", 3)))
        self.max_interval_spin.setValue(int(cfg.get("max_interval", 6)))
        self.dry_run_check.setChecked(False)
        self.load_summary()
