"""AutoWriter 桌面应用入口模块。"""
from __future__ import annotations

# 标准库导入
import sys
from pathlib import Path

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt

# 确保包根目录在模块搜索路径中
CURRENT_DIR = Path(__file__).resolve().parent
PARENT_DIR = CURRENT_DIR.parent
if str(PARENT_DIR) not in sys.path:
    sys.path.insert(0, str(PARENT_DIR))

# 项目内部导入
from autowriter_desktop.app import create_application
from autowriter_desktop.core import paths
from autowriter_desktop.ui.main_window import MainWindow


def main() -> int:
    """程序主入口。"""
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling)
    app = create_application()
    app.setApplicationName("AutoWriter")
    app.setOrganizationName("AutoWriter")
    app.setWindowIcon(QIcon(str(paths.asset_path("icons.svg"))))
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
