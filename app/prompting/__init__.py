"""提示词管理模块，集中处理多版本 Prompt 与质量闸门。"""

from .registry import get_prompt, choose_prompt_variant  # noqa: F401
from .guards import QualityReport, evaluate_quality  # noqa: F401
