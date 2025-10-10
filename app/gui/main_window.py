# -*- coding: utf-8 -*-  # 指定 UTF-8 编码以兼容中文注释
"""定义 AutoWriter 桌面应用的主窗口，负责协调控制器与各个自定义组件。"""  # 模块说明文档字符串

from __future__ import annotations  # 启用未来注解语法提升类型提示灵活度

import logging  # 访问标准日志库以注入自定义 Handler
from pathlib import Path  # 统一处理资源路径
from typing import Callable  # 为回调定义清晰签名

from PySide6.QtCore import QObject, Qt, Signal, QTimer  # Qt 基础类型、信号与定时器
from PySide6.QtGui import QAction, QIcon  # 工具栏动作与图标支持
from PySide6.QtWidgets import (  # Qt 部件集合用于构建界面
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QSizePolicy,
    QSplitter,
    QStatusBar,
    QTabWidget,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from app.gui.controllers.generator_controller import GeneratorController  # 导入生成任务控制器
from app.gui.controllers.monitor_controller import MonitorController  # 导入监控控制器
from app.gui.controllers.publisher_controller import PublisherController  # 导入投递控制器
from app.gui.controllers.settings_controller import SettingsController  # 导入设置控制器
from app.gui.widgets.article_viewer import ArticleViewer  # 草稿预览组件
from app.gui.widgets.cookie_manager import CookieManager  # Cookie 管理组件
from app.gui.widgets.log_viewer import LogViewer  # 实时日志组件
from app.gui.widgets.report_viewer import ReportViewer  # 报表展示组件
from app.gui.widgets.status_panel import StatusPanel  # 系统状态面板
from app.utils.logger import get_logger  # 引入统一日志模块

LOGGER = get_logger(__name__)  # 初始化当前模块记录器


class _LogSignalEmitter(QObject):  # 自定义 QObject 以通过信号转发日志
    """用于跨线程将日志字符串安全传递给界面。"""  # 类说明

    log_signal = Signal(str)  # 定义信号携带日志文本


class QtLogHandler(logging.Handler):  # 自定义日志处理器将消息发往 Qt 信号
    """将 Python 日志转发到 GUI。"""  # 类说明

    def __init__(self) -> None:  # 构造函数
        super().__init__()  # 调用父类初始化
        self.emitter = _LogSignalEmitter()  # 创建信号发射器实例

    def emit(self, record: logging.LogRecord) -> None:  # 重写 emit 方法
        message = self.format(record)  # 格式化日志记录
        self.emitter.log_signal.emit(message)  # 通过信号发送日志文本


class StatusIndicator(QWidget):  # 自定义状态指示灯控件
    """使用彩色圆点展示当前任务状态。"""  # 类说明

    def __init__(self, parent: QWidget | None = None) -> None:  # 构造函数
        super().__init__(parent)  # 初始化 QWidget 基类
        layout = QHBoxLayout(self)  # 创建水平布局
        layout.setContentsMargins(4, 0, 4, 0)  # 设置边距让控件贴边
        self.dot = QLabel("●")  # 使用文本圆点表示状态
        self.dot.setStyleSheet("color: gray; font-size: 18px;")  # 默认灰色表示空闲
        self.label = QLabel("空闲")  # 状态文字默认空闲
        layout.addWidget(self.dot)  # 添加圆点到布局
        layout.addWidget(self.label)  # 添加文字描述
        layout.addStretch()  # 占位扩展保持右对齐
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)  # 固定高度

    def set_state(self, color: str, text: str) -> None:  # 更新状态显示
        self.dot.setStyleSheet(f"color: {color}; font-size: 18px;")  # 更新圆点颜色
        self.label.setText(text)  # 更新文字


class MainWindow(QMainWindow):  # 主窗口类
    """负责组织工具栏、侧边栏、日志窗口与控制器。"""  # 类说明

    def __init__(self) -> None:  # 构造函数
        super().__init__()  # 调用父类初始化
        self.setWindowTitle("AutoWriter 控制台")  # 设置窗口标题
        self.resize(1280, 720)  # 设置默认窗口尺寸
        self.log_viewer = LogViewer()  # 实例化日志窗口
        self.status_panel = StatusPanel()  # 实例化状态面板
        self.cookie_manager = CookieManager()  # 实例化 Cookie 管理面板
        self.article_viewer = ArticleViewer()  # 实例化文章预览组件
        self.report_viewer = ReportViewer()  # 实例化报表组件
        self.tabs = QTabWidget()  # 创建中心标签页容器
        self.status_indicator = StatusIndicator()  # 创建状态指示灯
        self.qt_handler = QtLogHandler()  # 创建 Qt 日志处理器
        self.refresh_timer: QTimer | None = None  # 定时器引用用于定期刷新
        self._setup_logging_bridge()  # 注册日志信号桥梁
        self._build_toolbar()  # 构建顶部工具栏
        self._build_layout()  # 构建主界面布局
        self._build_status_bar()  # 构建底部状态栏
        self._init_controllers()  # 初始化控制器并连接信号
        self._start_auto_refresh()  # 启动自动刷新定时器
        self.monitor_controller.refresh_status()  # 首次刷新状态
        self.settings_controller.refresh_cookie_info()  # 首次同步 Cookie 信息

    def _setup_logging_bridge(self) -> None:  # 将日志信号连接到 LogViewer
        self.qt_handler.setLevel(logging.DEBUG)  # 设置处理器输出级别
        formatter = logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")  # 定义日志格式
        self.qt_handler.setFormatter(formatter)  # 绑定格式化器
        self.qt_handler.emitter.log_signal.connect(self.log_viewer.append_log)  # 将信号接入日志窗口

    def _attach_logger(self, logger: logging.Logger) -> None:  # 将 GUI 处理器附加到指定 logger
        if self.qt_handler not in logger.handlers:  # 避免重复添加
            logger.addHandler(self.qt_handler)  # 添加日志处理器

    def _build_toolbar(self) -> None:  # 构建顶部工具栏
        toolbar = QToolBar("主工具栏", self)  # 创建工具栏实例
        toolbar.setMovable(False)  # 固定工具栏避免拖动
        icon_dir = Path(__file__).resolve().parent / "resources" / "icons"  # 计算图标目录
        generate_action = QAction(QIcon(str(icon_dir / "run.svg")), "📝 生成文章", self)  # 创建生成按钮
        generate_action.triggered.connect(self._on_generate_clicked)  # 绑定点击事件
        publish_action = QAction(QIcon(str(icon_dir / "wechat.svg")), "📤 投递草稿", self)  # 创建投递按钮
        publish_action.triggered.connect(self._on_publish_clicked)  # 绑定点击事件
        report_action = QAction(QIcon(str(icon_dir / "zhihu.svg")), "📊 导出报表", self)  # 创建报表按钮
        report_action.triggered.connect(self._on_report_clicked)  # 绑定点击事件
        refresh_action = QAction(QIcon(str(icon_dir / "refresh.svg")), "🔄 刷新状态", self)  # 创建刷新按钮
        refresh_action.triggered.connect(self._on_refresh_clicked)  # 绑定点击事件
        toolbar.addAction(generate_action)  # 添加生成按钮到工具栏
        toolbar.addAction(publish_action)  # 添加投递按钮
        toolbar.addAction(report_action)  # 添加报表按钮
        toolbar.addAction(refresh_action)  # 添加刷新按钮
        toolbar.addSeparator()  # 添加分隔符将状态灯推至右侧
        toolbar.addWidget(self.status_indicator)  # 在工具栏右侧放置状态指示灯
        self.addToolBar(toolbar)  # 将工具栏添加到主窗口

    def _build_layout(self) -> None:  # 构建中心布局
        central = QWidget(self)  # 创建中心容器
        root_layout = QVBoxLayout(central)  # 使用垂直布局组织组件
        splitter = QSplitter(Qt.Horizontal, central)  # 水平分割器负责左右布局
        left_panel = QWidget(splitter)  # 左侧容器
        left_layout = QVBoxLayout(left_panel)  # 左侧垂直布局
        left_layout.addWidget(self.status_panel)  # 上方放置状态面板
        left_layout.addWidget(self.cookie_manager)  # 下方放置 Cookie 面板
        splitter.addWidget(left_panel)  # 将左侧容器加入分割器
        self.tabs.addTab(self.article_viewer, "草稿预览")  # 添加草稿预览标签页
        self.tabs.addTab(self.report_viewer, "报表分析")  # 添加报表标签页
        splitter.addWidget(self.tabs)  # 将标签页加入分割器
        splitter.setStretchFactor(0, 1)  # 左侧宽度权重
        splitter.setStretchFactor(1, 2)  # 中央区域更宽
        root_layout.addWidget(splitter, stretch=3)  # 顶部区域占更大比例
        root_layout.addWidget(self.log_viewer, stretch=1)  # 底部日志窗口
        self.setCentralWidget(central)  # 设置中心部件

    def _start_auto_refresh(self) -> None:  # 启动定时刷新任务
        if self.refresh_timer is None:  # 避免重复创建
            self.refresh_timer = QTimer(self)  # 创建定时器
            self.refresh_timer.setInterval(60000)  # 设置 60 秒
            self.refresh_timer.timeout.connect(self.monitor_controller.refresh_status)  # 定时刷新系统状态
            self.refresh_timer.timeout.connect(self.settings_controller.refresh_cookie_info)  # 定时刷新 Cookie
            self.refresh_timer.start()  # 启动定时器

    def _build_status_bar(self) -> None:  # 构建底部状态栏
        status_bar = QStatusBar(self)  # 创建状态栏
        status_bar.showMessage("准备就绪")  # 设置默认提示
        self.setStatusBar(status_bar)  # 安装状态栏

    def _init_controllers(self) -> None:  # 初始化控制器并连接信号
        log_callback: Callable[[str], None] = self.log_viewer.append_log  # 定义日志回调
        status_callback: Callable[[str, str], None] = self._update_indicator  # 定义状态灯回调
        self.generator_controller = GeneratorController(log_callback, status_callback)  # 构造生成控制器
        self.publisher_controller = PublisherController(log_callback, status_callback, self.report_viewer)  # 构造投递控制器
        self.monitor_controller = MonitorController(log_callback, self.status_panel)  # 构造监控控制器
        self.settings_controller = SettingsController(log_callback, self.cookie_manager, self.status_panel)  # 构造设置控制器
        for controller in (  # 遍历所有控制器并附加 GUI 日志处理器
            self.generator_controller,
            self.publisher_controller,
            self.monitor_controller,
            self.settings_controller,
        ):
            self._attach_logger(controller.logger)  # 附加日志处理器
        self.cookie_manager.set_controller(self.settings_controller)  # 将控制器注入到 Cookie 管理组件
        self.report_viewer.set_controller(self.publisher_controller)  # 将控制器注入报表组件

    def _update_indicator(self, color: str, text: str) -> None:  # 更新状态指示灯
        self.status_indicator.set_state(color, text)  # 调用指示灯控件
        self.statusBar().showMessage(text)  # 同步更新状态栏提示

    def _on_generate_clicked(self) -> None:  # 响应生成按钮
        self.generator_controller.start_generation()  # 调用生成控制器

    def _on_publish_clicked(self) -> None:  # 响应投递按钮
        self.publisher_controller.start_publish()  # 调用投递控制器

    def _on_report_clicked(self) -> None:  # 响应导出报表按钮
        try:
            self.publisher_controller.export_report()  # 调用报表导出逻辑
            QMessageBox.information(self, "导出完成", "报表已导出并更新到面板")  # 弹窗提示成功
        except Exception as exc:  # noqa: BLE001  # 捕获异常提示用户
            QMessageBox.critical(self, "导出失败", str(exc))  # 弹窗显示错误信息
            LOGGER.exception("导出报表失败 error=%s", exc)  # 将异常写入日志

    def _on_refresh_clicked(self) -> None:  # 响应刷新按钮
        self.monitor_controller.refresh_status()  # 刷新系统状态
        self.settings_controller.refresh_cookie_info()  # 更新 Cookie 信息

    def closeEvent(self, event) -> None:  # 在窗口关闭时执行清理
        for controller in (
            self.generator_controller,
            self.publisher_controller,
            self.monitor_controller,
            self.settings_controller,
        ):
            controller.shutdown()  # 请求控制器停止后台线程
        super().closeEvent(event)  # 调用父类关闭处理
