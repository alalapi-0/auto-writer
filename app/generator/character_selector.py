"""角色选择工具，负责加载与检索角色库。"""

from __future__ import annotations

import json
import random
from functools import lru_cache
from typing import Dict, List, Optional, Tuple

from config.settings import BASE_DIR

CHARACTER_FILE_PATH = BASE_DIR / "app" / "generator" / "characters.json"


class CharacterSelectorError(ValueError):
    """当角色库数据非法或存在重复时抛出。"""


def _validate_character_entry(entry: Dict[str, object]) -> Dict[str, object]:
    """校验单个角色条目结构与数据类型。"""

    if "name" not in entry or "work" not in entry or "traits" not in entry:
        raise CharacterSelectorError("角色条目缺少必需字段 name/work/traits")
    name = entry["name"]
    work = entry["work"]
    traits = entry["traits"]
    if not isinstance(name, str) or not name.strip():
        raise CharacterSelectorError("name 字段必须为非空字符串")
    if not isinstance(work, str) or not work.strip():
        raise CharacterSelectorError("work 字段必须为非空字符串")
    if not isinstance(traits, list) or not traits:
        raise CharacterSelectorError("traits 字段必须为非空列表")
    cleaned_traits: List[str] = []
    for trait in traits:
        if not isinstance(trait, str) or not trait.strip():
            raise CharacterSelectorError("traits 列表内的元素必须为非空字符串")
        cleaned_traits.append(trait.strip())
    return {
        "name": name.strip(),
        "work": work.strip(),
        "traits": cleaned_traits,
    }


@lru_cache(maxsize=1)
def _load_characters() -> List[Dict[str, object]]:
    """读取角色库文件并进行基础校验。"""

    raw_text = CHARACTER_FILE_PATH.read_text(encoding="utf-8")
    data = json.loads(raw_text)
    if not isinstance(data, list):
        raise CharacterSelectorError("角色库顶层结构必须为数组")
    characters: List[Dict[str, object]] = []
    seen: set[Tuple[str, str]] = set()
    for entry in data:
        if not isinstance(entry, dict):
            raise CharacterSelectorError("角色条目必须是对象结构")
        validated = _validate_character_entry(entry)
        key = (validated["name"], validated["work"])
        if key in seen:
            raise CharacterSelectorError(
                f"检测到重复角色组合: {validated['name']} @ {validated['work']}"
            )
        seen.add(key)
        characters.append(validated)
    return characters


def get_random_character() -> Dict[str, object]:
    """随机返回一个角色信息字典。"""

    characters = _load_characters()
    selected = random.choice(characters)
    return {
        "name": selected["name"],
        "work": selected["work"],
        "traits": list(selected["traits"]),
    }


def get_character_by_name(name: str) -> Optional[Dict[str, object]]:
    """根据角色名精确查找角色，未命中返回 None。"""

    if not isinstance(name, str):
        raise TypeError("name 参数必须为字符串")
    for character in _load_characters():
        if character["name"] == name:
            return {
                "name": character["name"],
                "work": character["work"],
                "traits": list(character["traits"]),
            }
    return None


def ensure_unique_characters() -> None:
    """对外暴露的校验入口，确保角色组合唯一。"""

    _load_characters()
