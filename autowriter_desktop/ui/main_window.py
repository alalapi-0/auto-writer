"""主窗口定义。"""
from __future__ import annotations

from typing import Dict, Any

from PySide6.QtWidgets import (
    QMainWindow,
    QWidget,
    QHBoxLayout,
    QVBoxLayout,
    QPushButton,
    QStackedWidget,
    QLabel,
    QMessageBox,
)

from ..core import config as config_module
from .pages.dashboard_page import DashboardPage
from .pages.generate_export_page import GenerateExportPage
from .pages.auto_draft_page import AutoDraftPage
from .pages.logs_page import LogsPage
from .pages.settings_page import SettingsPage


class MainWindow(QMainWindow):
    """应用主窗口。"""

    def __init__(self) -> None:
        super().__init__()
        self._config: Dict[str, Any] = config_module.load_config()
        self.setWindowTitle("AutoWriter 桌面版")
        self.resize(1280, 800)
        self._status_label = QLabel(self)
        self._stack = QStackedWidget(self)
        self._nav_buttons: list[QPushButton] = []
        self._setup_ui()
        self.refresh_status_bar()

    def _setup_ui(self) -> None:
        """构建主界面。"""
        central = QWidget(self)
        layout = QHBoxLayout(central)
        nav_widget = QWidget(central)
        nav_layout = QVBoxLayout(nav_widget)
        nav_layout.setContentsMargins(0, 0, 0, 0)
        nav_layout.setSpacing(8)

        pages = [
            ("仪表盘", DashboardPage(self)),
            ("生成/导出", GenerateExportPage(self)),
            ("自动送草稿", AutoDraftPage(self)),
            ("日志与截图", LogsPage(self)),
            ("设置", SettingsPage(self)),
        ]
        for index, (label, widget) in enumerate(pages):
            button = QPushButton(label, nav_widget)
            button.setCheckable(True)
            button.clicked.connect(lambda checked, idx=index: self._on_nav_clicked(idx))
            nav_layout.addWidget(button)
            self._stack.addWidget(widget)
            self._nav_buttons.append(button)
        nav_layout.addStretch(1)

        layout.addWidget(nav_widget, 0)
        layout.addWidget(self._stack, 1)
        self.setCentralWidget(central)
        self.statusBar().addPermanentWidget(self._status_label, 1)
        self._on_nav_clicked(0)

    def _on_nav_clicked(self, index: int) -> None:
        """切换页面。"""
        for i, button in enumerate(self._nav_buttons):
            button.setChecked(i == index)
        self._stack.setCurrentIndex(index)
        widget = self._stack.currentWidget()
        if hasattr(widget, "on_page_activated"):
            getattr(widget, "on_page_activated")()

    def refresh_status_bar(self) -> None:
        """刷新底部状态信息。"""
        cfg = self._config
        text = (
            f"导出目录: {cfg.get('export_root')}  |  "
            f"CDP 端口: {cfg.get('cdp_port')}  |  "
            f"默认生成数: {cfg.get('default_count')}"
        )
        self._status_label.setText(text)

    @property
    def config(self) -> Dict[str, Any]:
        """当前配置。"""
        return self._config

    def update_config(self, new_config: Dict[str, Any]) -> None:
        """保存并刷新配置。"""
        self._config.update(new_config)
        config_module.save_config(self._config)
        self.refresh_status_bar()

    def reload_config(self) -> None:
        """重新加载配置。"""
        self._config = config_module.load_config()
        self.refresh_status_bar()

    def notify(self, message: str) -> None:
        """统一弹窗。"""
        QMessageBox.information(self, "AutoWriter", message)
