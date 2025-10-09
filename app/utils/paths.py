# app/utils/paths.py
# 说明：提供跨平台应用数据目录的统一入口，所有可变数据（DB/导出/日志/临时）都从这里派生。
from __future__ import annotations  # TODO: 确保兼容未来类型注解，避免运行时报错
import os  # TODO: 访问环境变量，支持 Windows APPDATA
import platform  # TODO: 检测当前操作系统类型，决定目录位置
from pathlib import Path  # TODO: 使用 Path 对象处理路径，提升可读性


def get_app_data_dir() -> Path:
    """
    返回 AutoWriter 在本机的应用数据根目录（跨平台）：
    - macOS: ~/Library/Application Support/AutoWriter/
    - Windows: %USERPROFILE%\\AppData\\Roaming\\AutoWriter\\
    - Linux/其他: ~/.autowriter/
    如不存在则自动创建。
    """
    system = platform.system().lower()  # TODO: 获取系统标识，统一为小写，防止判断错误
    home = Path.home()  # TODO: 获取用户主目录，作为默认基准
    if "darwin" in system or "mac" in system:  # TODO: 判断是否为 macOS
        base = home / "Library" / "Application Support" / "AutoWriter"  # TODO: 拼接 macOS 指定目录
    elif "windows" in system:  # TODO: 判断是否为 Windows 平台
        base = Path(os.environ.get("APPDATA", str(home / "AppData" / "Roaming"))) / "AutoWriter"  # TODO: 兼容 APPDATA 缺失场景
    else:  # TODO: 其余视为类 Unix 系统
        base = home / ".autowriter"  # TODO: Linux 默认隐藏目录，避免污染家目录
    base.mkdir(parents=True, exist_ok=True)  # TODO: 确保目录存在，不存在则创建
    return base  # TODO: 返回统一的 Path 对象，供调用方使用


def ensure_subdir(name: str) -> Path:
    """
    在应用数据根目录下创建指定子目录并返回其 Path。
    例如：ensure_subdir("data") / ensure_subdir("logs")
    """
    d = get_app_data_dir() / name  # TODO: 拼接子目录路径，继承根目录
    d.mkdir(parents=True, exist_ok=True)  # TODO: 确保子目录存在，可多级创建
    return d  # TODO: 返回子目录 Path，方便上层继续拼接
