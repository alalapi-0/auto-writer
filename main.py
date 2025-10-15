"""AutoWriter 交互式主程序入口。"""

from __future__ import annotations

import argparse
import os
from typing import Dict

from autowriter_text.configuration import load_config
from autowriter_text.pipeline.run_batch import run_batch
from cli import cmd_auto


def _clear_cached_config() -> None:
    """在切换提供商时清理配置缓存。"""

    try:
        load_config.cache_clear()  # type: ignore[attr-defined]
    except AttributeError:
        pass


def _prompt_choice(title: str, options: Dict[str, str]) -> str:
    """基于控制台交互从选项中选择。"""

    print(f"\n{title}")
    for idx, (value, label) in enumerate(options.items(), start=1):
        print(f"  {idx}. {label}")
    reverse = {str(idx): value for idx, value in enumerate(options.keys(), start=1)}
    while True:
        choice = input("请输入选项编号: ").strip().lower()
        if choice in reverse:
            return reverse[choice]
        if choice in options:
            return choice
        print("无效选择，请重新输入。")


def _prompt_optional(prompt: str, default: str | None = None) -> str | None:
    """带默认值的输入提示。"""

    suffix = f" (默认: {default})" if default is not None else ""
    value = input(f"{prompt}{suffix}: ").strip()
    if not value:
        return default
    return value


def _prompt_bool(prompt: str, default: bool = False) -> bool:
    """解析布尔输入。"""

    default_text = "Y/n" if default else "y/N"
    value = input(f"{prompt} ({default_text}): ").strip().lower()
    if not value:
        return default
    return value in {"y", "yes", "true", "1"}


def _prompt_int(prompt: str, default: int) -> int:
    """读取整数输入。"""

    while True:
        raw = _prompt_optional(prompt, str(default))
        if raw is None:
            return default
        try:
            return int(raw)
        except ValueError:
            print("请输入有效的整数。")


def _prompt_float(prompt: str, default: float) -> float:
    """读取浮点数输入。"""

    while True:
        raw = _prompt_optional(prompt, f"{default}")
        if raw is None:
            return default
        try:
            return float(raw)
        except ValueError:
            print("请输入有效的数字。")


def _warn_missing_credentials(provider: str) -> None:
    """在缺少关键凭据时给出提示。"""

    if provider == "openai" and not os.getenv("OPENAI_API_KEY"):
        print("[提示] 未检测到 OPENAI_API_KEY，生成时将退回占位内容。")
    if provider == "vps" and (not os.getenv("VPS_API_KEY") or not os.getenv("VPS_API_BASE_URL")):
        print("[提示] 未检测到 VPS_API_KEY 或 VPS_API_BASE_URL，生成时将退回占位内容。")


def _run_automation_flow() -> None:
    """引导用户选择自动化流程参数。"""

    platform = _prompt_choice(
        "请选择要自动化的平台:",
        {"wechat": "微信公众号", "zhihu": "知乎", "both": "两个平台都执行"},
    )
    date_str = _prompt_optional("请输入素材日期 (YYYY-MM-DD 留空代表今日)")
    limit = _prompt_int("每个平台投递篇数", 5)
    dry_run = _prompt_bool("是否仅演练不提交", False)
    max_retries = _prompt_int("单篇最大重试次数", 3)
    min_interval = _prompt_float("跨篇最短等待 (秒)", 6.0)
    max_interval = _prompt_float("跨篇最长等待 (秒)", 12.0)
    cdp_url = _prompt_optional("Chrome DevTools 连接地址", "http://127.0.0.1:9222")

    args = argparse.Namespace(
        platform=platform,
        date=date_str,
        limit=limit,
        dry_run=dry_run,
        max_retries=max_retries,
        min_interval=min_interval,
        max_interval=max_interval,
        cdp=cdp_url,
    )
    cmd_auto(args)


def main() -> None:
    """程序入口。"""

    print("欢迎使用 AutoWriter 主程序 ✨")
    while True:
        provider = _prompt_choice(
            "请选择要使用的模型提供商:",
            {
                "openai": "OpenAI API",
                "vps": "VPS 实例 API",
                "ollama": "Ollama (本地)",
                "vllm": "vLLM 服务",
                "groq": "Groq 云端",
                "fireworks": "Fireworks AI",
                "hf_endpoint": "Hugging Face Endpoint",
            },
        )
        os.environ["AUTOWRITER_LLM_PROVIDER"] = provider
        _clear_cached_config()
        config = load_config()
        print(
            "当前配置 → provider=%s, model=%s, base_url=%s"
            % (config.llm.provider, config.llm.model, config.llm.base_url or "<默认>")
        )
        _warn_missing_credentials(provider)

        action = _prompt_choice(
            "请选择要执行的操作:",
            {"generate": "运行批量生成", "auto": "执行投放自动化", "exit": "退出程序"},
        )
        if action == "generate":
            results = run_batch()
            print(f"完成，本次生成成功 {len(results)} 篇。")
        elif action == "auto":
            _run_automation_flow()
        else:
            print("感谢使用，再见！")
            break

        if not _prompt_bool("是否继续执行其他操作?", True):
            print("感谢使用，再见！")
            break


if __name__ == "__main__":
    main()
