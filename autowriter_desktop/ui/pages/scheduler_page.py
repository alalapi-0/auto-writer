"""定时任务配置页面。"""
from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import QTime
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QFormLayout,
    QCheckBox,
    QTimeEdit,
    QComboBox,
    QLineEdit,
    QSpinBox,
    QPushButton,
    QMessageBox,
    QLabel,
)

from ...core import scheduler


class SchedulerPage(QWidget):
    """提供图形化的计划任务配置入口。"""

    def __init__(self, main_window) -> None:
        super().__init__(main_window)
        # 保存主窗口引用，便于访问配置
        self.main_window = main_window
        # 初始化控件
        self.enable_check = QCheckBox("启用定时任务", self)
        self.time_edit = QTimeEdit(self)
        self.frequency_combo = QComboBox(self)
        self.custom_days_edit = QLineEdit(self)
        self.command_combo = QComboBox(self)
        self.custom_cli_edit = QLineEdit(self)
        self.fail_retry_spin = QSpinBox(self)
        self.fail_interval_spin = QSpinBox(self)
        self.save_button = QPushButton("保存并创建", self)
        self.disable_button = QPushButton("停用任务", self)
        self.run_button = QPushButton("立即执行一次", self)
        self.status_button = QPushButton("查看状态", self)
        self.status_label = QLabel(self)
        # 构建界面
        self._build_ui()
        # 加载初始配置
        self._load_values()
        # 刷新状态展示
        self._refresh_status()

    def _build_ui(self) -> None:
        """构建控件布局。"""

        # 页面主布局
        layout = QVBoxLayout(self)
        # 表单布局承载各项配置
        form = QFormLayout()

        # 时间选择控件配置为 24 小时制
        self.time_edit.setDisplayFormat("HH:mm")
        form.addRow("执行时间", self.time_edit)

        # 周期选择下拉框
        self.frequency_combo.addItem("每日", "daily")
        self.frequency_combo.addItem("工作日", "weekdays")
        self.frequency_combo.addItem("自定义星期", "custom")
        form.addRow("执行频率", self.frequency_combo)

        # 自定义星期输入提示
        self.custom_days_edit.setPlaceholderText("例：1,3,5 表示周一三五")
        form.addRow("自定义星期", self.custom_days_edit)

        # 执行内容选择
        self.command_combo.addItem("全流程", "full")
        self.command_combo.addItem("仅送草稿", "auto_only")
        self.command_combo.addItem("自定义命令", "custom")
        form.addRow("运行内容", self.command_combo)

        # 自定义命令输入框
        self.custom_cli_edit.setPlaceholderText("支持使用 {date} 占位日期")
        form.addRow("自定义 CLI", self.custom_cli_edit)

        # 失败重试设置
        self.fail_retry_spin.setRange(0, 10)
        form.addRow("失败重试次数", self.fail_retry_spin)

        # 间隔设置
        self.fail_interval_spin.setRange(5, 3600)
        form.addRow("重试间隔(秒)", self.fail_interval_spin)

        # 将表单加入主布局
        layout.addWidget(self.enable_check)
        layout.addLayout(form)

        # 按钮区域
        layout.addWidget(self.save_button)
        layout.addWidget(self.disable_button)
        layout.addWidget(self.run_button)
        layout.addWidget(self.status_button)
        layout.addWidget(self.status_label)
        layout.addStretch(1)

        # 信号绑定
        self.save_button.clicked.connect(self._save)
        self.disable_button.clicked.connect(self._disable)
        self.run_button.clicked.connect(self._run_once)
        self.status_button.clicked.connect(self._show_status)
        self.frequency_combo.currentIndexChanged.connect(self._update_custom_visibility)
        self.command_combo.currentIndexChanged.connect(self._update_custom_visibility)

    def _load_values(self) -> None:
        """从配置文件加载设置。"""

        cfg = self.main_window.config
        self.enable_check.setChecked(bool(cfg.get("schedule_enabled", False)))
        time_value = cfg.get("schedule_time", "09:00")
        try:
            hour, minute = map(int, str(time_value).split(":"))
        except ValueError:
            hour, minute = 9, 0
        self.time_edit.setTime(QTime(hour, minute))
        days_value = cfg.get("schedule_days", "daily")
        index = max(0, self.frequency_combo.findData(days_value))
        self.frequency_combo.setCurrentIndex(index)
        self.custom_days_edit.setText(str(cfg.get("schedule_custom_days", "")))
        cmd_value = cfg.get("schedule_cmd", "full")
        cmd_index = max(0, self.command_combo.findData(cmd_value))
        self.command_combo.setCurrentIndex(cmd_index)
        self.custom_cli_edit.setText(str(cfg.get("schedule_custom_cli", "")))
        self.fail_retry_spin.setValue(int(cfg.get("fail_retry", 0)))
        self.fail_interval_spin.setValue(int(cfg.get("fail_interval", 60)))
        self._update_custom_visibility()

    def _gather_config(self) -> dict[str, object]:
        """收集界面上的配置项。"""

        return {
            "schedule_enabled": self.enable_check.isChecked(),
            "schedule_time": self.time_edit.time().toString("HH:mm"),
            "schedule_days": self.frequency_combo.currentData(),
            "schedule_custom_days": self.custom_days_edit.text(),
            "schedule_cmd": self.command_combo.currentData(),
            "schedule_custom_cli": self.custom_cli_edit.text(),
            "fail_retry": self.fail_retry_spin.value(),
            "fail_interval": self.fail_interval_spin.value(),
        }

    def _save(self) -> None:
        """保存并尝试创建计划任务。"""

        cfg = self._gather_config()
        self.main_window.update_config(cfg)
        if cfg["schedule_enabled"]:
            try:
                scheduler.create_task(self.main_window.config)
            except Exception as exc:  # noqa: BLE001
                QMessageBox.critical(self, "AutoWriter", f"创建计划任务失败：{exc}")
                self.enable_check.setChecked(False)
                self.main_window.update_config({"schedule_enabled": False})
                return
            QMessageBox.information(self, "AutoWriter", "计划任务已保存，请在系统计划任务中确认")
        else:
            QMessageBox.information(self, "AutoWriter", "已保存设置，如需启用请勾选开关")
        self._refresh_status()

    def _disable(self) -> None:
        """停用计划任务。"""

        try:
            scheduler.remove_task()
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "AutoWriter", f"停用时出现异常：{exc}")
        cfg = self._gather_config()
        cfg["schedule_enabled"] = False
        self.enable_check.setChecked(False)
        self.main_window.update_config(cfg)
        QMessageBox.information(self, "AutoWriter", "计划任务已停用")
        self._refresh_status()

    def _run_once(self) -> None:
        """立即触发执行一次。"""

        try:
            scheduler.run_now()
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "AutoWriter", f"触发执行失败：{exc}")
            return
        QMessageBox.information(self, "AutoWriter", "已发送立即执行指令")

    def _show_status(self) -> None:
        """弹窗展示当前状态。"""

        try:
            status = scheduler.task_status()
        except Exception as exc:  # noqa: BLE001
            status = f"查询失败：{exc}"
        QMessageBox.information(self, "AutoWriter", status)

    def _update_custom_visibility(self) -> None:
        """根据选择显示/隐藏额外输入。"""

        is_custom_days = self.frequency_combo.currentData() == "custom"
        self.custom_days_edit.setVisible(is_custom_days)
        is_custom_cmd = self.command_combo.currentData() == "custom"
        self.custom_cli_edit.setVisible(is_custom_cmd)

    def _refresh_status(self) -> None:
        """刷新下次运行时间信息。"""

        next_run = scheduler.calculate_next_run(self.main_window.config, datetime.now())
        if not self.main_window.config.get("schedule_enabled"):
            text = "定时任务未启用"
        elif next_run is None:
            text = "无法计算下次运行时间，请检查设置"
        else:
            text = f"下次预估运行时间：{next_run.strftime('%Y-%m-%d %H:%M')}"
        self.status_label.setText(text)

    def on_page_activated(self) -> None:
        """页面被激活时刷新显示。"""

        self._load_values()
        self._refresh_status()
