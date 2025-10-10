# -*- coding: utf-8 -*-  # 指定 UTF-8 编码
"""设置控制器，负责 Cookie 管理与配置展示。"""  # 模块说明

from __future__ import annotations  # 启用未来注解

import json  # 读取 Cookie 文件
import subprocess  # 打开目录
import sys  # 判断操作系统
from datetime import datetime  # 格式化时间
from pathlib import Path  # 处理路径
from typing import Callable, Dict  # 类型注解

from PySide6.QtWidgets import QMessageBox  # 弹窗控件

from app.gui.widgets.cookie_manager import CookieManager  # Cookie 管理组件
from app.gui.widgets.status_panel import StatusPanel  # 状态面板组件
from app.utils.logger import get_logger  # 日志模块

LOGGER = get_logger(__name__)  # 初始化日志器


class SettingsController:  # 设置控制器
    """封装 Cookie 信息刷新与辅助操作。"""  # 类说明

    def __init__(
        self,
        log_callback: Callable[[str], None],
        widget: CookieManager,
        status_panel: StatusPanel | None = None,
    ) -> None:  # 构造函数
        self.log_callback = log_callback  # 保存日志回调
        self.widget = widget  # 保存组件引用
        self.status_panel = status_panel  # 保存状态面板引用
        self.logger = LOGGER  # 暴露日志器
        self.cookie_dir = Path(".sessions")  # Cookie 目录
        self.cookie_files = {  # 平台与文件映射
            "wechat": self.cookie_dir / "wechat_mp.cookies.json",
            "zhihu": self.cookie_dir / "zhihu.cookies.json",
        }

    def refresh_cookie_info(self) -> None:  # 刷新 Cookie 文件信息
        info = {name: self._inspect_cookie(path) for name, path in self.cookie_files.items()}  # 收集信息
        self.widget.update_cookie_info(info)  # 更新组件
        self._sync_status_panel(info)  # 同步状态面板

    def _inspect_cookie(self, path: Path) -> Dict[str, str]:  # 检查单个文件
        if not path.exists():  # 文件不存在
            return {"status": "❌ 未找到", "mtime": "-", "size": "0 B"}  # 返回默认信息
        stat = path.stat()  # 获取文件状态
        mtime = datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S")  # 格式化时间
        size = f"{stat.st_size} B"  # 构造大小
        return {"status": "✅ 存在", "mtime": mtime, "size": size}  # 返回信息

    def open_cookie_folder(self) -> None:  # 打开 Cookie 目录
        folder = self.cookie_dir.resolve()  # 计算绝对路径
        folder.mkdir(parents=True, exist_ok=True)  # 确保目录存在
        self.log_callback(f"[INFO] 打开目录: {folder}")  # 写入日志
        try:
            if sys.platform.startswith("darwin"):  # macOS
                subprocess.Popen(["open", str(folder)])  # 调用 open
            elif sys.platform.startswith("win"):  # Windows
                subprocess.Popen(["explorer", str(folder)])  # 调用 explorer
            else:  # Linux
                subprocess.Popen(["xdg-open", str(folder)])  # 调用 xdg-open
        except Exception as exc:  # noqa: BLE001  # 捕获异常
            self.logger.warning("打开目录失败 error=%s", exc)  # 记录警告
            QMessageBox.warning(None, "打开失败", f"请手动访问: {folder}")  # 提示用户

    def check_cookie(self, platform: str) -> None:  # 检测 Cookie 有效性
        path = self.cookie_files.get(platform)  # 获取文件路径
        if path is None:  # 未知平台
            QMessageBox.warning(None, "未知平台", platform)  # 弹窗提示
            return  # 返回
        if not path.exists():  # 文件不存在
            QMessageBox.warning(None, "未找到 Cookie", f"请先扫码登录 {platform}")  # 提示
            return  # 返回
        try:
            data = json.loads(path.read_text(encoding="utf-8"))  # 加载 JSON
        except json.JSONDecodeError:  # 解析失败
            QMessageBox.critical(None, "Cookie 无效", "JSON 文件损坏，请重新扫码")  # 提示
            return  # 返回
        expires = self._guess_expiry(data)  # 推测过期时间
        self.log_callback(f"[INFO] {platform} Cookie 校验通过，过期时间 {expires}")  # 写入日志
        QMessageBox.information(None, "检测完成", f"{platform} Cookie 正常，过期时间 {expires}")  # 弹窗

    def _guess_expiry(self, data: Dict) -> str:  # 推测过期时间
        if isinstance(data, dict):  # 确认类型
            timestamps = []  # 收集时间戳
            for value in data.values():  # 遍历值
                if isinstance(value, dict) and "expires" in value:  # 包含过期字段
                    timestamps.append(value["expires"])  # 收集
            if timestamps:  # 若存在
                try:
                    ts = max(int(float(item)) for item in timestamps)  # 取最大值
                    return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M")  # 格式化
                except Exception:  # noqa: BLE001  # 捕获转换异常
                    return "未知"  # 返回未知
        return "未知"  # 默认未知

    def relogin(self, platform: str) -> None:  # 提示重新扫码
        self.log_callback(f"[INFO] 请在弹出的浏览器中完成 {platform} 扫码登录")  # 写入日志
        QMessageBox.information(None, "扫码登录", f"示例暂未集成自动扫码，请手动更新 {platform} Cookie")  # 提示

    def delete_cookie(self, platform: str) -> None:  # 删除 Cookie 文件
        path = self.cookie_files.get(platform)  # 获取文件
        if path and path.exists():  # 如果存在
            path.unlink()  # 删除文件
            self.log_callback(f"[INFO] 已删除 {platform} Cookie 文件")  # 写入日志
        self.refresh_cookie_info()  # 刷新显示

    def _sync_status_panel(self, info: Dict[str, Dict[str, str]]) -> None:  # 同步状态面板
        if self.status_panel is None:  # 若未注入状态面板
            return  # 直接返回
        parts = [f"{name}:{payload['status']}" for name, payload in info.items()]  # 组合文本
        summary = " | ".join(parts) if parts else "未检测"  # 合并
        self.status_panel.update_cookie_status(summary)  # 更新状态标签
