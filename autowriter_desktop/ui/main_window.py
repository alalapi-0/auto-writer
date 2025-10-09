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
    QCheckBox,
)

from ..core import config as config_module
from ..core import scheduler
from ..core.notify import TrayNotifier
from .pages.dashboard_page import DashboardPage
from .pages.generate_export_page import GenerateExportPage
from .pages.auto_draft_page import AutoDraftPage
from .pages.logs_page import LogsPage
from .pages.settings_page import SettingsPage
from .pages.scheduler_page import SchedulerPage


class MainWindow(QMainWindow):
    """应用主窗口。"""

    def __init__(self) -> None:
        super().__init__()
        self._config: Dict[str, Any] = config_module.load_config()
        self.setWindowTitle("AutoWriter 桌面版")
        self.resize(1280, 800)
        self._status_label = QLabel(self)
        self._next_run_label = QLabel(self)
        self._schedule_toggle = QCheckBox("定时任务", self)
        self._schedule_toggle.stateChanged.connect(self._on_schedule_toggle)
        self._updating_toggle = False
        self._stack = QStackedWidget(self)
        self._nav_buttons: list[QPushButton] = []
        self.tray = TrayNotifier(self)
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
            ("定时任务", SchedulerPage(self)),
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
        self.statusBar().addPermanentWidget(self._schedule_toggle)
        self.statusBar().addPermanentWidget(self._next_run_label)
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
        self._update_schedule_widgets()

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

    def _update_schedule_widgets(self) -> None:
        """同步状态栏中的定时任务信息。"""

        self._updating_toggle = True
        self._schedule_toggle.setChecked(bool(self._config.get("schedule_enabled")))
        self._updating_toggle = False
        next_run = scheduler.calculate_next_run(self._config)
        if next_run:
            self._next_run_label.setText(f"下次运行：{next_run.strftime('%m-%d %H:%M')}")
        else:
            self._next_run_label.setText("下次运行：--")

    def _on_schedule_toggle(self, state: int) -> None:
        """切换状态栏的计划任务开关。"""

        if self._updating_toggle:
            return
        enabled = state == 2
        new_cfg = {"schedule_enabled": enabled}
        self.update_config(new_cfg)
        try:
            if enabled:
                scheduler.create_task(self._config)
                self.notify("已尝试创建定时任务")
            else:
                scheduler.remove_task()
                self.notify("已请求停用定时任务")
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "AutoWriter", f"操作失败：{exc}")
        self.refresh_status_bar()
