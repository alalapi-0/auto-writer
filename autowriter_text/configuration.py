"""加载并缓存 AutoWriter Text 的配置文件。"""

from __future__ import annotations

import os
from dataclasses import asdict, dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Literal

try:  # pragma: no cover - 兼容缺少 PyYAML 的环境
    import yaml  # 解析 YAML 配置
except ImportError:  # pragma: no cover
    yaml = None  # type: ignore[assignment]

from dotenv import load_dotenv  # 加载 .env 文件

from autowriter_text.logging import logger


@dataclass
class LLMConfig:
    """大模型相关配置。"""

    provider: Literal[
        "ollama",
        "vllm",
        "groq",
        "fireworks",
        "hf_endpoint",
        "openai",
        "wps",
    ] = "ollama"
    model: str = "llama3.1:8b"
    temperature: float = 0.4
    max_tokens: int = 3000
    timeout_s: int = 120
    base_url: str | None = None

    def copy(self, **updates: object) -> "LLMConfig":
        """返回更新后的副本。"""

        data = asdict(self)
        data.update(updates)
        base_url = data.get("base_url")
        if isinstance(base_url, str):
            base_url = base_url.strip() or None
            data["base_url"] = base_url
        return LLMConfig(**data)


@dataclass
class DedupConfig:
    """去重策略配置。"""

    scope: Literal["daily", "global"] = "daily"


@dataclass
class BatchConfig:
    """批处理相关配置。"""

    count: int = 5


@dataclass
class AppConfig:
    """整体配置封装。"""

    llm: LLMConfig = field(default_factory=LLMConfig)
    dedup: DedupConfig = field(default_factory=DedupConfig)
    batch: BatchConfig = field(default_factory=BatchConfig)
    database_path: str | None = None

    def copy(self, **updates: object) -> "AppConfig":
        """返回替换字段后的副本。"""

        data = asdict(self)
        data.update(updates)
        data["llm"] = LLMConfig(**data["llm"]) if isinstance(data["llm"], dict) else data["llm"]
        data["dedup"] = DedupConfig(**data["dedup"]) if isinstance(data["dedup"], dict) else data["dedup"]
        data["batch"] = BatchConfig(**data["batch"]) if isinstance(data["batch"], dict) else data["batch"]
        return AppConfig(**data)


def _config_path() -> Path:
    """返回 config.yaml 的绝对路径。"""

    return Path(__file__).resolve().parent / "config.yaml"


def _merge_llm(llm: LLMConfig, raw: dict[str, object]) -> LLMConfig:
    """根据字典更新 LLMConfig。"""

    updates = {k: raw[k] for k in ["provider", "model", "temperature", "max_tokens", "timeout_s", "base_url"] if k in raw}
    return llm.copy(**updates)


def _merge_config(config: AppConfig, data: dict[str, object]) -> AppConfig:
    """将原始字典合并到 AppConfig。"""

    updated = config
    if "llm" in data and isinstance(data["llm"], dict):
        updated = updated.copy(llm=_merge_llm(config.llm, data["llm"]))
    if "dedup" in data and isinstance(data["dedup"], dict):
        scope = data["dedup"].get("scope", config.dedup.scope)
        updated = updated.copy(dedup=DedupConfig(scope=scope))
    if "batch" in data and isinstance(data["batch"], dict):
        count = int(data["batch"].get("count", config.batch.count))
        updated = updated.copy(batch=BatchConfig(count=count))
    if "database_path" in data and isinstance(data["database_path"], str):
        updated = updated.copy(database_path=data["database_path"])
    return updated


@lru_cache(maxsize=1)
def load_config() -> AppConfig:
    """加载配置文件并应用 .env 覆盖。"""

    load_dotenv()
    config = AppConfig()
    config_file = _config_path()
    data: dict[str, object] = {}
    if config_file.exists():
        if yaml is not None:
            data = yaml.safe_load(config_file.read_text(encoding="utf-8")) or {}
        else:
            logger.warning("PyYAML 未安装，使用默认配置值")
    if isinstance(data, dict):
        config = _merge_config(config, data)

    provider_override = os.getenv("AUTOWRITER_LLM_PROVIDER")
    if isinstance(provider_override, str) and provider_override.strip():
        provider_name = provider_override.strip().lower()
        allowed_providers = {
            "ollama",
            "vllm",
            "groq",
            "fireworks",
            "hf_endpoint",
            "openai",
            "wps",
        }
        if provider_name in allowed_providers:
            config = config.copy(llm=config.llm.copy(provider=provider_name))

    env_mapping = {
        "ollama": "OLLAMA_BASE_URL",
        "vllm": "VLLM_BASE_URL",
        "openai": "OPENAI_BASE_URL",
        "wps": "WPS_API_BASE_URL",
    }
    env_key = env_mapping.get(config.llm.provider)
    candidate = os.getenv(env_key) if env_key else None
    if not candidate:
        candidate = os.getenv("LLM_BASE_URL")
    if candidate:
        config = config.copy(llm=config.llm.copy(base_url=candidate))

    if not config.database_path:
        default_path = (Path(__file__).resolve().parent / "autowriter.db").resolve()
        config = config.copy(database_path=str(default_path))
    return config


__all__ = ["AppConfig", "LLMConfig", "DedupConfig", "BatchConfig", "load_config"]
