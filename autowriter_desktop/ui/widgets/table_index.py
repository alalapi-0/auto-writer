"""导出索引表格展示。"""
from __future__ import annotations

import csv
import os
import sys
from pathlib import Path
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QTableWidget,
    QTableWidgetItem,
    QLabel,
    QMessageBox,
)

from ...core import paths


class TableIndexWidget(QWidget):
    """读取 index.csv 并展示。"""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._hint = QLabel("选择日期后加载 index.csv", self)
        self._table = QTableWidget(self)
        self._table.setColumnCount(0)
        self._table.setRowCount(0)
        self._table.setEditTriggers(QTableWidget.NoEditTriggers)
        self._table.setSelectionBehavior(QTableWidget.SelectRows)
        self._table.setSelectionMode(QTableWidget.SingleSelection)
        self._table.doubleClicked.connect(self._open_selected_row)

        layout = QVBoxLayout(self)
        layout.addWidget(self._hint)
        layout.addWidget(self._table)

    def load_index(self, platform: str, date: str) -> None:
        """加载指定平台、日期的 index.csv。"""
        if platform == "all":
            candidates = [paths.exports_dir(date=date, platform=p) for p in ("wechat", "zhihu", "toutiao")]
            base_dir = None
            for candidate in candidates:
                csv_candidate = candidate / "index.csv"
                if csv_candidate.exists():
                    base_dir = candidate
                    break
            if base_dir is None:
                base_dir = paths.exports_dir(date=date, platform=None)
        else:
            base_dir = paths.exports_dir(date=date, platform=platform)
        csv_path = base_dir / "index.csv"
        if not csv_path.exists():
            self._hint.setText(f"未找到 {csv_path}")
            self._table.setRowCount(0)
            self._table.setColumnCount(0)
            return
        with csv_path.open("r", encoding="utf-8") as fh:
            reader = list(csv.reader(fh))
        if not reader:
            self._hint.setText("index.csv 为空")
            return
        header, *rows = reader
        self._table.setColumnCount(len(header))
        self._table.setHorizontalHeaderLabels(header)
        self._table.setRowCount(len(rows))
        self._current_dir = base_dir
        for r_index, row in enumerate(rows):
            for c_index, cell in enumerate(row):
                item = QTableWidgetItem(cell)
                self._table.setItem(r_index, c_index, item)
        self._hint.setText(str(csv_path))
        self._table.resizeColumnsToContents()

    def _open_selected_row(self) -> None:
        """打开当前选中行对应的目录。"""
        if not hasattr(self, "_current_dir"):
            return
        row = self._table.currentRow()
        if row < 0:
            return
        target = self._current_dir
        open_path_in_explorer(target)


def open_path_in_explorer(path: Path) -> None:
    """跨平台打开目录。"""
    if sys.platform.startswith("win"):
        os.startfile(path)
    elif sys.platform == "darwin":
        subprocess = __import__("subprocess")
        subprocess.call(["open", str(path)])
    else:
        subprocess = __import__("subprocess")
        try:
            subprocess.call(["xdg-open", str(path)])
        except FileNotFoundError:
            QMessageBox.information(None, "AutoWriter", f"请手动打开目录：{path}")
