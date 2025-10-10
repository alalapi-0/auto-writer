# -*- coding: utf-8 -*-  # 指定 UTF-8 编码
"""实时日志显示组件，支持级别过滤与自动滚动。"""  # 模块说明

from __future__ import annotations  # 启用未来注解

from typing import List, Tuple  # 类型注解

from PySide6.QtWidgets import (  # Qt 控件
    QComboBox,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class LogViewer(QWidget):  # 日志查看器
    """封装 QPlainTextEdit 提供过滤功能。"""  # 类说明

    def __init__(self, parent: QWidget | None = None) -> None:  # 构造函数
        super().__init__(parent)  # 初始化父类
        self._records: List[Tuple[str, str]] = []  # 保存日志记录 (level, text)
        self._build_ui()  # 构建界面

    def _build_ui(self) -> None:  # 初始化界面
        layout = QVBoxLayout(self)  # 垂直布局
        control_bar = QHBoxLayout()  # 顶部控制栏
        control_bar.addWidget(QLabel("日志级别:"))  # 添加标签
        self.filter_box = QComboBox(self)  # 创建下拉框
        self.filter_box.addItems(["全部", "INFO", "WARNING", "ERROR"])  # 添加选项
        self.filter_box.currentTextChanged.connect(self._apply_filter)  # 绑定过滤事件
        control_bar.addWidget(self.filter_box)  # 加入布局
        self.clear_button = QPushButton("清空", self)  # 创建清空按钮
        self.clear_button.clicked.connect(self.clear_logs)  # 绑定清空动作
        control_bar.addWidget(self.clear_button)  # 添加按钮
        control_bar.addStretch()  # 拉伸占位
        layout.addLayout(control_bar)  # 将控制栏加入主布局
        self.editor = QPlainTextEdit(self)  # 创建文本编辑器
        self.editor.setReadOnly(True)  # 设为只读
        self.editor.setLineWrapMode(QPlainTextEdit.NoWrap)  # 禁止自动换行
        layout.addWidget(self.editor)  # 加入主布局

    def append_log(self, text: str) -> None:  # 追加日志
        level = self._extract_level(text)  # 提取级别
        self._records.append((level, text))  # 保存记录
        if self._match_filter(level):  # 判断是否显示
            self.editor.appendPlainText(text)  # 追加内容
            self.editor.verticalScrollBar().setValue(self.editor.verticalScrollBar().maximum())  # 滚动到底

    def clear_logs(self) -> None:  # 清空日志
        self._records.clear()  # 清除缓存
        self.editor.clear()  # 清空文本

    def _extract_level(self, text: str) -> str:  # 提取日志级别
        for level in ("ERROR", "WARNING", "WARN", "INFO", "DEBUG"):  # 遍历候选
            token = f"[{level}]"  # 构造匹配标记
            if token in text:  # 若文本包含
                return "WARNING" if level == "WARN" else level  # 统一 WARN 为 WARNING
        return "INFO"  # 默认 INFO

    def _match_filter(self, level: str) -> bool:  # 判断是否匹配当前过滤
        current = self.filter_box.currentText()  # 获取选择
        if current == "全部":  # 全部时直接通过
            return True  # 返回 True
        return level == current  # 仅当级别一致

    def _apply_filter(self, _: str) -> None:  # 重新渲染日志
        self.editor.clear()  # 清空显示
        for level, text in self._records:  # 遍历记录
            if self._match_filter(level):  # 判断过滤
                self.editor.appendPlainText(text)  # 追加文本
        self.editor.verticalScrollBar().setValue(self.editor.verticalScrollBar().maximum())  # 保持滚动到底
