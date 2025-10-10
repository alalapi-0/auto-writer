# -*- coding: utf-8 -*-  # 指定 UTF-8 编码
"""文章预览组件，显示 outbox 目录树与内容预览。"""  # 模块说明

from __future__ import annotations  # 启用未来注解

from pathlib import Path  # 处理路径

from PySide6.QtCore import QItemSelection, Qt, QUrl  # Qt 核心类型
from PySide6.QtGui import QDesktopServices  # 打开外部程序
from PySide6.QtWidgets import (  # Qt 控件
    QApplication,
    QHBoxLayout,
    QPushButton,
    QSplitter,
    QTreeView,
    QVBoxLayout,
    QWidget,
    QPlainTextEdit,
    QFileSystemModel,
)

from config.settings import OUTBOX_DIR  # 导入 outbox 配置


class ArticleViewer(QWidget):  # 文章预览组件
    """展示 outbox 目录树并支持预览选中文件。"""  # 类说明

    def __init__(self, parent: QWidget | None = None) -> None:  # 构造函数
        super().__init__(parent)  # 初始化父类
        self.outbox_dir = Path(OUTBOX_DIR).expanduser()  # 解析 outbox 目录
        self.current_file: Path | None = None  # 当前选中文件
        self._build_ui()  # 构建界面
        self._load_model()  # 加载目录模型

    def _build_ui(self) -> None:  # 构建界面
        layout = QVBoxLayout(self)  # 主垂直布局
        splitter = QSplitter(Qt.Horizontal, self)  # 水平分割器
        self.model = QFileSystemModel(self)  # 文件系统模型
        self.model.setReadOnly(True)  # 设置只读
        self.tree = QTreeView(splitter)  # 左侧树视图
        self.tree.setModel(self.model)  # 绑定模型
        self.tree.setHeaderHidden(True)  # 隐藏表头
        self.tree.selectionModel().selectionChanged.connect(self._on_selection_changed)  # 绑定选择事件
        right_container = QWidget(splitter)  # 右侧容器
        right_layout = QVBoxLayout(right_container)  # 右侧垂直布局
        button_bar = QHBoxLayout()  # 顶部按钮
        open_button = QPushButton("打开所在文件夹", right_container)  # 打开按钮
        open_button.clicked.connect(self._open_folder)  # 绑定事件
        copy_button = QPushButton("复制路径", right_container)  # 复制按钮
        copy_button.clicked.connect(self._copy_path)  # 绑定事件
        button_bar.addWidget(open_button)  # 添加按钮
        button_bar.addWidget(copy_button)  # 添加按钮
        button_bar.addStretch()  # 占位
        right_layout.addLayout(button_bar)  # 添加按钮栏
        self.preview = QPlainTextEdit(right_container)  # 文本预览框
        self.preview.setReadOnly(True)  # 设置只读
        right_layout.addWidget(self.preview)  # 添加预览框
        splitter.addWidget(self.tree)  # 将树加入分割器
        splitter.addWidget(right_container)  # 将右侧容器加入
        splitter.setStretchFactor(0, 1)  # 设置伸缩因子
        splitter.setStretchFactor(1, 2)  # 右侧更大
        layout.addWidget(splitter)  # 将分割器放入主布局

    def _load_model(self) -> None:  # 加载目录模型
        self.outbox_dir.mkdir(parents=True, exist_ok=True)  # 确保目录存在
        root = self.model.setRootPath(str(self.outbox_dir))  # 设置根路径
        self.tree.setRootIndex(root)  # 绑定根节点
        self.tree.expandAll()  # 展开全部节点

    def _on_selection_changed(self, selected: QItemSelection, _: QItemSelection) -> None:  # 选择变化
        indexes = selected.indexes()  # 获取索引
        if not indexes:  # 无选择
            return  # 返回
        index = indexes[0]  # 取第一个
        file_path = Path(self.model.filePath(index))  # 获取路径
        if file_path.is_file():  # 仅处理文件
            self.current_file = file_path  # 记录当前文件
            try:
                content = file_path.read_text(encoding="utf-8")  # 读取内容
            except Exception:  # noqa: BLE001  # 读取失败
                content = "无法读取文件内容"  # 回退文本
            self.preview.setPlainText(content)  # 更新预览
        else:
            self.current_file = None  # 清理当前文件
            self.preview.clear()  # 清空预览

    def _open_folder(self) -> None:  # 打开所在文件夹
        target = self.current_file.parent if self.current_file else self.outbox_dir  # 确定目录
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(target)))  # 调用系统打开

    def _copy_path(self) -> None:  # 复制路径
        if not self.current_file:  # 若未选中文件
            return  # 不执行
        clipboard = QApplication.clipboard()  # 获取剪贴板
        clipboard.setText(str(self.current_file))  # 复制路径
