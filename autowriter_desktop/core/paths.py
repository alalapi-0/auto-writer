"""路径工具函数，集中管理桌面应用使用的文件位置。"""
from __future__ import annotations

from pathlib import Path
from datetime import datetime

import yaml

BASE_DIR = Path(__file__).resolve().parent.parent
PROJECT_ROOT = BASE_DIR.parent
HOME_DIR = Path.home()
CONFIG_DIR = HOME_DIR / ".autowriter"
CONFIG_FILE = CONFIG_DIR / "config.yaml"
EXPORTS_DIR = PROJECT_ROOT / "exports"
AUTOMATION_LOGS_DIR = PROJECT_ROOT / "automation_logs"
ASSETS_DIR = BASE_DIR / "assets"


def ensure_runtime_directories() -> None:
    """创建运行时依赖的目录。"""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    (CONFIG_DIR / "logs").mkdir(parents=True, exist_ok=True)
    export_root = get_export_root()
    export_root.mkdir(parents=True, exist_ok=True)
    AUTOMATION_LOGS_DIR.mkdir(parents=True, exist_ok=True)


def config_file() -> Path:
    """配置文件路径。"""
    return CONFIG_FILE


def runtime_log_file() -> Path:
    """应用运行日志文件。"""
    return CONFIG_DIR / "logs" / "app.log"


def asset_path(name: str) -> Path:
    """获取资源文件路径。"""
    return ASSETS_DIR / name


def exports_dir(date: str | None = None, platform: str | None = None) -> Path:
    """返回导出目录。"""
    path = get_export_root()
    if platform:
        path /= platform
    if date is None:
        date = datetime.now().strftime("%Y-%m-%d")
    path /= date
    return path


def automation_log_dir(date: str | None = None) -> Path:
    """返回自动送草稿日志目录。"""
    if date is None:
        date = datetime.now().strftime("%Y-%m-%d")
    return AUTOMATION_LOGS_DIR / date


def get_export_root() -> Path:
    """读取配置文件中的导出根目录。"""
    try:
        if CONFIG_FILE.exists():
            with CONFIG_FILE.open("r", encoding="utf-8") as fh:
                data = yaml.safe_load(fh) or {}
                custom = data.get("export_root")
                if custom:
                    return Path(custom)
    except Exception:  # noqa: BLE001
        pass
    return EXPORTS_DIR
