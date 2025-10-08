"""日志与截图浏览页面。"""
from __future__ import annotations

import json
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QWidget,
    QHBoxLayout,
    QVBoxLayout,
    QListWidget,
    QListWidgetItem,
    QLabel,
    QScrollArea,
)

from ...core import paths
from ..widgets.table_index import open_path_in_explorer


class LogsPage(QWidget):
    """浏览自动化日志与截图。"""

    def __init__(self, main_window) -> None:
        super().__init__(main_window)
        self.date_list = QListWidget(self)
        self.summary_label = QLabel(self)
        self.summary_label.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self.summary_label.setWordWrap(True)
        self.image_area = QScrollArea(self)
        self.image_area.setWidgetResizable(True)
        self.image_container = QWidget(self.image_area)
        self.image_layout = QVBoxLayout(self.image_container)
        self.image_layout.addStretch(1)
        self.image_area.setWidget(self.image_container)
        self._setup_ui()
        self.refresh_dates()

    def _setup_ui(self) -> None:
        layout = QHBoxLayout(self)
        self.date_list.itemSelectionChanged.connect(self._on_date_selected)
        self.date_list.itemDoubleClicked.connect(self._open_selected_dir)
        layout.addWidget(self.date_list, 1)

        right_panel = QVBoxLayout()
        right_panel.addWidget(self.summary_label)
        right_panel.addWidget(self.image_area, 1)

        container = QWidget(self)
        container.setLayout(right_panel)
        layout.addWidget(container, 3)

    def refresh_dates(self) -> None:
        self.date_list.clear()
        logs_dir = paths.AUTOMATION_LOGS_DIR
        if not logs_dir.exists():
            return
        dates = sorted([p.name for p in logs_dir.iterdir() if p.is_dir()], reverse=True)
        for date in dates:
            item = QListWidgetItem(date)
            self.date_list.addItem(item)
        if dates:
            self.date_list.setCurrentRow(0)

    def _on_date_selected(self) -> None:
        items = self.date_list.selectedItems()
        if not items:
            return
        date = items[0].text()
        self.load_logs(date)

    def load_logs(self, date: str) -> None:
        log_dir = paths.automation_log_dir(date)
        summary_path = log_dir / "summary.json"
        if summary_path.exists():
            with summary_path.open("r", encoding="utf-8") as fh:
                data = json.load(fh)
            summary_lines = [f"日期：{date}"]
            for key in ("success", "failed", "skipped"):
                summary_lines.append(f"{key}: {len(data.get(key, []))}")
            self.summary_label.setText("\n".join(summary_lines))
        else:
            self.summary_label.setText(f"{date} 暂无 summary.json，可点击打开目录查看原始日志。")
        self._populate_images(log_dir)

    def _populate_images(self, log_dir: Path) -> None:
        # 清空旧的缩略图控件
        while self.image_layout.count():
            item = self.image_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        screenshots = sorted(log_dir.glob("*.png"))
        if not screenshots:
            label = QLabel("暂无截图", self.image_container)
            self.image_layout.addWidget(label)
        else:
            for shot in screenshots:
                pixmap = QPixmap(str(shot))
                if pixmap.isNull():
                    continue
                scaled = pixmap.scaled(400, 400, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                label = QLabel(self.image_container)
                label.setPixmap(scaled)
                label.setToolTip(str(shot))
                self.image_layout.addWidget(label)
        open_button = QLabel(
            f"双击左侧日期可在文件管理器中打开：{log_dir}", self.image_container
        )
        open_button.setWordWrap(True)
        self.image_layout.addWidget(open_button)
        self.image_layout.addStretch(1)

    def _open_selected_dir(self, *_) -> None:
        items = self.date_list.selectedItems()
        if not items:
            return
        log_dir = paths.automation_log_dir(items[0].text())
        open_path_in_explorer(log_dir)

    def on_page_activated(self) -> None:
        self.refresh_dates()
