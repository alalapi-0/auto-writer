"""为项目提供统一的 logger，自动降级到标准库 logging。"""

from __future__ import annotations

import logging

try:  # pragma: no cover - 仅在 loguru 存在时执行
    from loguru import logger as _logger
except ImportError:  # pragma: no cover - 测试环境可能缺少 loguru
    logging.basicConfig(level=logging.INFO)
    _logger = logging.getLogger("autowriter_text")

logger = _logger

__all__ = ["logger"]
