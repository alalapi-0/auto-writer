# -*- coding: utf-8 -*-  # 指定 UTF-8 编码
"""Cookie 管理面板，提供文件状态与操作按钮。"""  # 模块说明

from __future__ import annotations  # 启用未来注解

from typing import Dict  # 类型注解

from PySide6.QtWidgets import (  # Qt 控件
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class CookieManager(QWidget):  # Cookie 管理组件
    """展示 Cookie 文件信息并转发操作到控制器。"""  # 类说明

    def __init__(self, parent: QWidget | None = None) -> None:  # 构造函数
        super().__init__(parent)  # 初始化父类
        self.controller = None  # 控制器引用
        self.labels: Dict[str, Dict[str, QLabel]] = {}  # 存放各平台的标签
        self._build_ui()  # 构建界面

    def _build_ui(self) -> None:  # 构建界面布局
        layout = QVBoxLayout(self)  # 主垂直布局
        header_bar = QHBoxLayout()  # 顶部按钮行
        open_button = QPushButton("打开 Cookie 目录", self)  # 打开目录按钮
        open_button.clicked.connect(self._open_folder)  # 绑定事件
        header_bar.addWidget(open_button)  # 添加按钮
        header_bar.addStretch()  # 占位
        layout.addLayout(header_bar)  # 将按钮行加入布局
        for platform, title in {"wechat": "微信公众号", "zhihu": "知乎"}.items():  # 遍历平台
            box = QGroupBox(f"{title} Cookie", self)  # 为每个平台创建分组
            grid = QGridLayout(box)  # 使用网格布局
            status_label = QLabel("状态: 未知", box)  # 状态标签
            mtime_label = QLabel("更新时间: 未知", box)  # 更新时间
            size_label = QLabel("文件大小: 未知", box)  # 大小
            grid.addWidget(status_label, 0, 0, 1, 2)  # 放置状态标签
            grid.addWidget(mtime_label, 1, 0, 1, 2)  # 放置时间标签
            grid.addWidget(size_label, 2, 0, 1, 2)  # 放置大小标签
            check_button = QPushButton("检测有效性", box)  # 检测按钮
            check_button.clicked.connect(lambda _, p=platform: self._check(p))  # 绑定事件
            relogin_button = QPushButton("重新扫码登录", box)  # 重登按钮
            relogin_button.clicked.connect(lambda _, p=platform: self._relogin(p))  # 绑定事件
            delete_button = QPushButton("删除缓存", box)  # 删除按钮
            delete_button.clicked.connect(lambda _, p=platform: self._delete(p))  # 绑定事件
            grid.addWidget(check_button, 3, 0)  # 放置检测按钮
            grid.addWidget(relogin_button, 3, 1)  # 放置重登按钮
            grid.addWidget(delete_button, 4, 0, 1, 2)  # 放置删除按钮
            self.labels[platform] = {  # 保存标签引用
                "status": status_label,
                "mtime": mtime_label,
                "size": size_label,
            }
            layout.addWidget(box)  # 将分组加入主布局
        layout.addStretch()  # 底部留白

    def set_controller(self, controller) -> None:  # 注入控制器
        self.controller = controller  # 保存引用

    def update_cookie_info(self, info: Dict[str, Dict[str, str]]) -> None:  # 更新显示
        for platform, payload in info.items():  # 遍历信息
            labels = self.labels.get(platform)  # 获取标签
            if not labels:  # 若未定义
                continue  # 跳过
            labels["status"].setText(f"状态: {payload.get('status', '未知')}")  # 更新状态
            labels["mtime"].setText(f"更新时间: {payload.get('mtime', '-')}")  # 更新时间
            labels["size"].setText(f"文件大小: {payload.get('size', '-')}")  # 更新大小

    def _open_folder(self) -> None:  # 打开目录
        if self.controller:  # 若已绑定控制器
            self.controller.open_cookie_folder()  # 调用控制器

    def _check(self, platform: str) -> None:  # 检测按钮回调
        if self.controller:  # 若已绑定控制器
            self.controller.check_cookie(platform)  # 调用控制器

    def _relogin(self, platform: str) -> None:  # 重新扫码回调
        if self.controller:  # 若已绑定控制器
            self.controller.relogin(platform)  # 调用控制器

    def _delete(self, platform: str) -> None:  # 删除按钮回调
        if self.controller:  # 若已绑定控制器
            self.controller.delete_cookie(platform)  # 调用控制器
