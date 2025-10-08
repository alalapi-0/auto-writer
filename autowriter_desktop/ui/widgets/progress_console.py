"""任务执行日志输出控件。"""
from __future__ import annotations

from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QTextEdit,
    QMessageBox,
)
from PySide6.QtGui import QTextCursor


class ProgressConsole(QWidget):
    """带复制按钮的文本输出区域。"""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._text = QTextEdit(self)
        self._text.setReadOnly(True)
        self._text.setLineWrapMode(QTextEdit.NoWrap)
        self._copy_button = QPushButton("复制全部", self)
        self._clear_button = QPushButton("清空", self)

        button_bar = QHBoxLayout()
        button_bar.addWidget(self._copy_button)
        button_bar.addWidget(self._clear_button)
        button_bar.addStretch(1)

        layout = QVBoxLayout(self)
        layout.addWidget(self._text)
        layout.addLayout(button_bar)

        self._copy_button.clicked.connect(self.copy_all)
        self._clear_button.clicked.connect(self.clear)

    def append_line(self, line: str) -> None:
        """追加一行文本并保持滚动到底部。"""
        self._text.append(line)
        cursor = self._text.textCursor()
        cursor.movePosition(QTextCursor.End)
        self._text.setTextCursor(cursor)
        self._text.ensureCursorVisible()

    def clear(self) -> None:
        """清空输出。"""
        self._text.clear()

    def copy_all(self) -> None:
        """复制全部文本到剪贴板。"""
        text = self._text.toPlainText()
        if not text:
            QMessageBox.information(self, "AutoWriter", "暂无可复制内容")
            return
        self._text.selectAll()
        self._text.copy()
        self._text.moveCursor(QTextCursor.End)
