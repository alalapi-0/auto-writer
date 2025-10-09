"""系统托盘通知工具。"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Optional

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QSystemTrayIcon, QStyle


class TrayNotifier(QSystemTrayIcon):
    """简单封装托盘消息通知。"""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        # 记录点击通知后需要打开的路径
        self._pending_path: Optional[Path] = None
        # 判断系统是否支持托盘
        self._available = QSystemTrayIcon.isSystemTrayAvailable()
        if not self._available:
            self.setVisible(False)
            return
        # 尝试复用应用风格图标，如果失败则保持空白
        app = QApplication.instance()
        if app:
            icon = app.style().standardIcon(QStyle.SP_ComputerIcon)
            self.setIcon(icon)
        else:
            self.setIcon(QIcon())
        # 设置提示文本
        self.setToolTip("AutoWriter 通知")
        # 显示托盘图标
        self.setVisible(True)
        # 绑定点击事件
        self.messageClicked.connect(self._handle_click)

    def show_info(self, title: str, body: str, onclick_path: str | None = None) -> None:
        """展示信息通知。"""

        # 重置待打开路径
        self._pending_path = Path(onclick_path).expanduser() if onclick_path else None
        # 弹出消息
        if self._available:
            self.showMessage(title, body, QSystemTrayIcon.Information)

    def _handle_click(self) -> None:
        """处理通知被点击的情况。"""

        if not self._pending_path:
            return
        self._open_path(self._pending_path)

    def _open_path(self, target: Path) -> None:
        """根据平台打开目录。"""

        if not target.exists():
            return
        if sys.platform.startswith("win"):
            subprocess.Popen(["explorer", str(target)])
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(target)])
        else:
            subprocess.Popen(["xdg-open", str(target)])
