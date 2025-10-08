"""设置页面。"""
from __future__ import annotations

from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QFormLayout,
    QSpinBox,
    QLineEdit,
    QPushButton,
    QCheckBox,
    QFileDialog,
)


class SettingsPage(QWidget):
    """提供配置项编辑功能。"""

    def __init__(self, main_window) -> None:
        super().__init__(main_window)
        self.main_window = main_window
        self.default_count_spin = QSpinBox(self)
        self.export_root_edit = QLineEdit(self)
        self.cdp_port_spin = QSpinBox(self)
        self.retry_spin = QSpinBox(self)
        self.min_interval_spin = QSpinBox(self)
        self.max_interval_spin = QSpinBox(self)
        self.dup_days_spin = QSpinBox(self)
        self.dup_threshold_spin = QSpinBox(self)
        self.delay_min_spin = QSpinBox(self)
        self.delay_max_spin = QSpinBox(self)
        self.continue_check = QCheckBox("失败后继续下一步", self)
        self.save_button = QPushButton("保存设置", self)
        self.choose_button = QPushButton("选择目录", self)
        self._setup_ui()
        self._load_values()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.default_count_spin.setRange(1, 50)
        form.addRow("默认生成条数", self.default_count_spin)

        export_widget = QWidget(self)
        export_row = QVBoxLayout(export_widget)
        export_row.setContentsMargins(0, 0, 0, 0)
        export_row.addWidget(self.export_root_edit)
        export_row.addWidget(self.choose_button)
        form.addRow("导出目录", export_widget)

        self.cdp_port_spin.setRange(1000, 65535)
        form.addRow("CDP 端口", self.cdp_port_spin)

        self.retry_spin.setRange(0, 10)
        form.addRow("最大重试次数", self.retry_spin)

        self.min_interval_spin.setRange(0, 120)
        form.addRow("最小间隔(秒)", self.min_interval_spin)

        self.max_interval_spin.setRange(0, 180)
        form.addRow("最大间隔(秒)", self.max_interval_spin)

        self.dup_days_spin.setRange(0, 30)
        form.addRow("去重天数", self.dup_days_spin)

        self.dup_threshold_spin.setRange(0, 100)
        form.addRow("去重阈值", self.dup_threshold_spin)

        self.delay_min_spin.setRange(0, 60)
        form.addRow("人类最小延迟", self.delay_min_spin)

        self.delay_max_spin.setRange(0, 120)
        form.addRow("人类最大延迟", self.delay_max_spin)

        form.addRow("失败后继续", self.continue_check)

        layout.addLayout(form)
        layout.addWidget(self.save_button)
        layout.addStretch(1)

        self.choose_button.clicked.connect(self._choose_export_dir)
        self.save_button.clicked.connect(self._save)

    def _load_values(self) -> None:
        cfg = self.main_window.config
        self.default_count_spin.setValue(int(cfg.get("default_count", 5)))
        self.export_root_edit.setText(cfg.get("export_root", ""))
        self.cdp_port_spin.setValue(int(cfg.get("cdp_port", 9222)))
        self.retry_spin.setValue(int(cfg.get("retry_max", 3)))
        self.min_interval_spin.setValue(int(cfg.get("min_interval", 3)))
        self.max_interval_spin.setValue(int(cfg.get("max_interval", 6)))
        self.dup_days_spin.setValue(int(cfg.get("dup_check_days", 7)))
        self.dup_threshold_spin.setValue(int(cfg.get("dup_threshold", 85)))
        self.delay_min_spin.setValue(int(cfg.get("human_delay_min", 1)))
        self.delay_max_spin.setValue(int(cfg.get("human_delay_max", 3)))
        self.continue_check.setChecked(bool(cfg.get("continue_on_error", False)))

    def _choose_export_dir(self) -> None:
        directory = QFileDialog.getExistingDirectory(self, "选择导出目录", self.export_root_edit.text())
        if directory:
            self.export_root_edit.setText(directory)

    def _save(self) -> None:
        cfg = {
            "default_count": self.default_count_spin.value(),
            "export_root": self.export_root_edit.text(),
            "cdp_port": self.cdp_port_spin.value(),
            "retry_max": self.retry_spin.value(),
            "min_interval": self.min_interval_spin.value(),
            "max_interval": self.max_interval_spin.value(),
            "dup_check_days": self.dup_days_spin.value(),
            "dup_threshold": self.dup_threshold_spin.value(),
            "human_delay_min": self.delay_min_spin.value(),
            "human_delay_max": self.delay_max_spin.value(),
            "continue_on_error": self.continue_check.isChecked(),
        }
        self.main_window.update_config(cfg)
        self.main_window.notify("设置已保存")

    def on_page_activated(self) -> None:
        self._load_values()
