# -*- coding: utf-8 -*-  # 指定 UTF-8 编码防止中文注释乱码
"""AutoWriter 桌面应用主入口，负责初始化 Qt 应用、加载样式并捕获全局异常。"""  # 中文文档字符串概述用途

from __future__ import annotations  # 启用未来注解语法增强类型提示灵活性

import sys  # 访问 Python 解释器系统级能力
import traceback  # 将异常堆栈格式化为字符串便于记录
from pathlib import Path  # 处理资源路径以兼容不同操作系统

from PySide6.QtWidgets import QApplication, QMessageBox  # Qt 应用与消息弹窗控件
from PySide6.QtGui import QIcon  # 提供窗口图标设置能力
from PySide6.QtCore import Qt  # 提供高 DPI 属性常量

try:  # 捕获 qdarkstyle 导入异常避免应用启动失败
    import qdarkstyle  # 深色主题库
except Exception:  # noqa: BLE001  # 捕获所有异常并降级为 None
    qdarkstyle = None  # 若导入失败则回退到自定义 QSS

from app.gui.main_window import MainWindow  # 导入自定义主窗口类
from app.utils.logger import get_logger  # 引入统一日志模块

LOGGER = get_logger(__name__)  # 初始化模块级日志记录器


def _handle_exception(exc_type, exc_value, exc_traceback) -> None:  # 自定义未捕获异常钩子
    """记录 Qt 主线程未捕获异常并提示用户。"""  # 中文文档字符串说明用途

    formatted = "".join(traceback.format_exception(exc_type, exc_value, exc_traceback))  # 格式化堆栈信息
    LOGGER.error("未处理异常\n%s", formatted)  # 将异常写入日志文件
    QMessageBox.critical(None, "AutoWriter 异常", formatted)  # 使用对话框提醒用户


def _apply_stylesheet(app: QApplication) -> None:  # 根据依赖加载深色或自定义主题
    """优先加载 qdarkstyle，其次尝试读取自定义 QSS。"""  # 中文文档字符串解释流程

    if qdarkstyle is not None:  # 如果成功导入 qdarkstyle
        app.setStyleSheet(qdarkstyle.load_stylesheet(qt_api="pyside6"))  # 应用官方深色主题
        LOGGER.debug("已加载 qdarkstyle 默认样式")  # 输出调试日志说明主题来源
        return  # 应用成功后直接返回
    qss_path = Path(__file__).with_suffix("").parent / "resources" / "style.qss"  # 计算 QSS 路径
    if qss_path.exists():  # 若自定义样式文件存在
        app.setStyleSheet(qss_path.read_text(encoding="utf-8"))  # 读取并设置样式
        LOGGER.debug("已加载自定义 QSS 样式 %s", qss_path)  # 记录样式路径
    else:  # 若没有可用样式文件
        LOGGER.warning("未找到 qdarkstyle 或 style.qss，将使用 Qt 默认主题")  # 输出警告以便排查


def main() -> int:  # 提供脚本执行入口
    """创建 Qt 应用并展示主窗口。"""  # 中文文档字符串描述行为

    sys.excepthook = _handle_exception  # 替换默认异常钩子以捕获主线程错误
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)  # 启用高 DPI 缩放支持
    app = QApplication(sys.argv)  # 构造 Qt 应用实例
    app.setApplicationName("AutoWriter App")  # 设置应用名称便于系统识别
    _apply_stylesheet(app)  # 加载主题样式
    window = MainWindow()  # 创建主窗口实例
    icon_path = Path(__file__).with_suffix("").parent / "resources" / "icons" / "run.svg"  # 复用运行图标作为应用图标
    if icon_path.exists():  # 若图标文件存在
        window.setWindowIcon(QIcon(str(icon_path)))  # 设置窗口图标
    window.show()  # 显示主窗口
    result = app.exec()  # 启动事件循环并等待退出
    LOGGER.info("AutoWriter GUI 退出 code=%s", result)  # 记录退出码
    return result  # 将退出码回传给调用方


if __name__ == "__main__":  # 允许直接运行模块
    sys.exit(main())  # 运行主入口并将返回码传给操作系统
