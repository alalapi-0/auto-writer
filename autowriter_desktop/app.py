"""AutoWriter 桌面端应用创建与全局异常处理。"""
from __future__ import annotations

import sys
import traceback
from datetime import datetime

from PySide6.QtWidgets import QApplication, QMessageBox

from .core import paths


def _exception_hook(exc_type, exc_value, exc_traceback) -> None:
    """捕获未处理异常并写入日志。"""
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return
    log_file = paths.runtime_log_file()
    log_file.parent.mkdir(parents=True, exist_ok=True)
    with log_file.open("a", encoding="utf-8") as fh:
        fh.write(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] 未捕获异常\n")
        traceback.print_exception(exc_type, exc_value, exc_traceback, file=fh)
        fh.write("\n")
    message = "应用出现未捕获异常，已写入日志：\n" + str(log_file)
    QMessageBox.critical(None, "AutoWriter", message)


def create_application() -> QApplication:
    """创建 QApplication 实例并安装异常钩子。"""
    paths.ensure_runtime_directories()
    app = QApplication(sys.argv)
    sys.excepthook = _exception_hook
    return app
