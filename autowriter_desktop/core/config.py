"""配置文件读写逻辑。"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

import yaml

from . import paths

DEFAULT_CONFIG: Dict[str, Any] = {
    "default_count": 5,
    "export_root": str(paths.EXPORTS_DIR),
    "cdp_port": 9222,
    "retry_max": 3,
    "min_interval": 3,
    "max_interval": 6,
    "dup_check_days": 7,
    "dup_threshold": 85,
    "human_delay_min": 1,
    "human_delay_max": 3,
    "continue_on_error": False,
}


def _ensure_file(path: Path) -> None:
    """确保配置文件存在。"""
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as fh:
            yaml.safe_dump(DEFAULT_CONFIG, fh, allow_unicode=True)


def load_config() -> Dict[str, Any]:
    """加载配置并自动填充默认值。"""
    cfg_path = paths.config_file()
    _ensure_file(cfg_path)
    with cfg_path.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    merged = DEFAULT_CONFIG.copy()
    merged.update(data)
    return merged


def save_config(config: Dict[str, Any]) -> None:
    """保存配置到磁盘。"""
    cfg_path = paths.config_file()
    cfg_path.parent.mkdir(parents=True, exist_ok=True)
    merged = DEFAULT_CONFIG.copy()
    merged.update(config)
    with cfg_path.open("w", encoding="utf-8") as fh:
        yaml.safe_dump(merged, fh, allow_unicode=True, sort_keys=False)
