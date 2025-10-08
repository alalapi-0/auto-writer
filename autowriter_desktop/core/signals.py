"""任务线程使用的信号定义。"""
from __future__ import annotations

from PySide6.QtCore import QObject, Signal


class TaskSignals(QObject):
    """通用任务信号。"""

    progress = Signal(str)
    finished = Signal(int)
    error = Signal(str)

    def __init__(self) -> None:
        super().__init__()
