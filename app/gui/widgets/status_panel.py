# -*- coding: utf-8 -*-  # 指定 UTF-8 编码
"""系统状态面板，展示 doctor 检查结果与关键指标。"""  # 模块说明

from __future__ import annotations  # 启用未来注解

from dataclasses import dataclass  # 定义数据结构
from typing import List  # 类型注解

from PySide6.QtWidgets import (  # Qt 控件
    QGridLayout,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)


@dataclass
class SimpleCheck:  # 用于表示检查结果
    name: str  # 检查项名称
    status: str  # 状态符号
    message: str  # 详细信息


class StatusPanel(QWidget):  # 状态面板
    """展示系统关键指标与 doctor 输出。"""  # 类说明

    def __init__(self, parent: QWidget | None = None) -> None:  # 构造函数
        super().__init__(parent)  # 初始化父类
        self._build_ui()  # 构建界面

    def _build_ui(self) -> None:  # 构建界面布局
        layout = QVBoxLayout(self)  # 垂直布局
        grid = QGridLayout()  # 顶部网格布局展示关键指标
        self.database_label = QLabel("数据库连接: 未知", self)  # 数据库状态标签
        self.outbox_label = QLabel("OUTBOX 目录: 未知", self)  # Outbox 状态标签
        self.cookie_label = QLabel("Cookie 状态: 未知", self)  # Cookie 状态标签
        self.theme_label = QLabel("未使用主题数: 未知", self)  # 主题库存标签
        self.article_label = QLabel("今日生成篇数: 未知", self)  # 今日产出标签
        grid.addWidget(self.database_label, 0, 0)  # 放置数据库标签
        grid.addWidget(self.outbox_label, 0, 1)  # 放置 Outbox 标签
        grid.addWidget(self.cookie_label, 1, 0)  # 放置 Cookie 标签
        grid.addWidget(self.theme_label, 1, 1)  # 放置主题标签
        grid.addWidget(self.article_label, 2, 0, 1, 2)  # 放置文章标签跨两列
        layout.addLayout(grid)  # 将网格加入主布局
        self.table = QTableWidget(self)  # 创建表格
        self.table.setColumnCount(3)  # 设置列数
        self.table.setHorizontalHeaderLabels(["状态", "检查项", "详情"])  # 设置表头
        self.table.horizontalHeader().setStretchLastSection(True)  # 最后一列自适应
        self.table.verticalHeader().setVisible(False)  # 隐藏行号
        layout.addWidget(self.table)  # 添加表格

    def update_checks(self, checks: List[SimpleCheck]) -> None:  # 更新表格内容
        self.table.setRowCount(len(checks))  # 设置行数
        for row, item in enumerate(checks):  # 遍历结果
            self.table.setItem(row, 0, QTableWidgetItem(item.status))  # 填写状态
            self.table.setItem(row, 1, QTableWidgetItem(item.name))  # 填写名称
            self.table.setItem(row, 2, QTableWidgetItem(item.message))  # 填写详情
        self._update_summary(checks)  # 更新顶部摘要

    def _update_summary(self, checks: List[SimpleCheck]) -> None:  # 根据检查更新摘要标签
        for item in checks:  # 遍历检查结果
            if "数据库连接" in item.name:  # 匹配数据库状态
                self.database_label.setText(f"数据库连接: {item.status} {item.message}")  # 更新标签
            elif "OUTBOX" in item.name.upper():  # 匹配 Outbox
                self.outbox_label.setText(f"OUTBOX 目录: {item.status} {item.message}")  # 更新标签
            elif "主题库存" in item.name:  # 匹配主题库存
                self.theme_label.setText(f"未使用主题数: {item.status} {item.message}")  # 更新标签
            elif "近 7 天消耗" in item.name:  # 匹配消耗记录
                self.article_label.setText(f"今日生成篇数: {item.status} {item.message}")  # 使用消耗信息代表近况
        # Cookie 状态由外部单独更新

    def update_cookie_status(self, text: str) -> None:  # 更新 Cookie 标签
        self.cookie_label.setText(f"Cookie 状态: {text}")  # 设置文本

    def update_error(self, message: str) -> None:  # 显示错误信息
        self.table.setRowCount(1)  # 设置单行
        self.table.setItem(0, 0, QTableWidgetItem("❌"))  # 状态列
        self.table.setItem(0, 1, QTableWidgetItem("系统自检"))  # 检查项
        self.table.setItem(0, 2, QTableWidgetItem(message))  # 详情
