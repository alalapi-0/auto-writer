"""Prompt 注册中心：负责加载不同版本的提示词模板并提供选择接口。"""

from __future__ import annotations  # 启用未来注解语法，保证类型注解字符串化

from pathlib import Path  # 处理模板目录
from typing import Dict, Iterable, Mapping, Tuple  # 类型提示

from app.prompting import strategies  # 引入策略模块用于挑选 Variant

PROMPTS_DIR = Path(__file__).parent / "prompts"  # 定义模板目录路径
_PROMPT_CACHE: Dict[str, str] = {}  # 缓存已加载的模板文本


def _load_all_prompts() -> Dict[str, str]:  # 内部函数：读取全部模板
    """扫描 prompts 目录并缓存所有 Prompt 文本。"""  # 中文注释

    if not _PROMPT_CACHE:  # 若缓存为空则执行加载
        for path in PROMPTS_DIR.glob("*.txt"):  # 遍历所有 txt 文件
            variant = path.stem  # 以文件名（去扩展名）作为 Variant 名称
            _PROMPT_CACHE[variant] = path.read_text(encoding="utf-8")  # 读取文件内容并缓存
    return _PROMPT_CACHE  # 返回缓存字典


def list_variants() -> Iterable[str]:  # 列出当前可用 Variant
    """返回所有已注册的 Prompt Variant 名称。"""  # 中文注释

    return _load_all_prompts().keys()  # 直接返回缓存字典的键集合


def get_prompt(variant: str) -> str:  # 根据 Variant 名称获取 Prompt
    """读取指定 Variant 的 Prompt 文本，不存在时抛出 KeyError。"""  # 中文注释

    prompts = _load_all_prompts()  # 确保缓存已加载
    if variant not in prompts:  # 检查 Variant 是否存在
        raise KeyError(f"未找到名为 {variant} 的 Prompt，请确认文件是否存在。")  # 抛出异常
    return prompts[variant]  # 返回对应模板


def choose_prompt_variant(  # 暴露统一接口供生成流程使用
    profile_config: Mapping[str, object] | None,  # Profile 配置，允许为空
    strategy_config: Mapping[str, object] | None = None,  # 策略配置，可选
) -> Tuple[str, str]:  # 返回选中的 Variant 名称与 Prompt 文本
    """根据策略配置挑选 Prompt Variant 并返回对应模板。"""  # 中文注释

    prompts = _load_all_prompts()  # 读取全部 Prompt
    if not prompts:  # 若无任何 Prompt
        raise RuntimeError("Prompt 注册中心为空，请先在 prompts 目录下放置模板文件。")  # 抛出异常提醒
    variant = strategies.select_variant(  # 调用策略模块选择 Variant
        list(prompts.keys()), profile_config, strategy_config
    )  # 传入可用 Variant 与配置
    return variant, prompts[variant]  # 返回 Variant 名称与模板文本
