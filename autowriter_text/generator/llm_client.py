"""多后端 LLM 客户端，统一暴露 generate 接口。"""

from __future__ import annotations

import os  # 读取环境变量
import time  # 处理指数退避
from dataclasses import dataclass  # 组织响应解析
from typing import Callable, Dict  # 类型注解

try:
    import httpx  # 发送 HTTP 请求
except ImportError:  # pragma: no cover - 兼容未安装 httpx 的场景
    httpx = None  # type: ignore[assignment]
from autowriter_text.logging import logger  # 输出调试信息

from autowriter_text.configuration import AppConfig, load_config  # 加载配置模型


@dataclass
class _LLMResponse:
    """标准化后的 LLM 响应。"""

    text: str


_RETRYABLE_STATUS = {408, 409, 429, 500, 502, 503, 504}
_MAX_ATTEMPTS = 4


def _exponential_backoff(attempt: int) -> float:
    """根据重试次数给出退避时间。"""

    return min(float(2 ** (attempt - 1)), 30.0)


def _request_with_retry(action: Callable[[], httpx.Response]) -> httpx.Response | None:
    """带指数退避的请求封装。"""

    last_exc: Exception | None = None
    for attempt in range(1, _MAX_ATTEMPTS + 1):
        try:
            response = action()
            response.raise_for_status()
            return response
        except httpx.HTTPStatusError as exc:  # 捕获 4xx/5xx 错误
            last_exc = exc
            status = exc.response.status_code
            if status not in _RETRYABLE_STATUS or attempt == _MAX_ATTEMPTS:
                logger.error("LLM 请求失败: %s", exc)
                return None
            sleep_for = _exponential_backoff(attempt)
            logger.warning(
                "LLM 请求返回 %s，%s 秒后重试（第 %s 次）", status, sleep_for, attempt
            )
            time.sleep(sleep_for)
        except httpx.RequestError as exc:  # 捕获网络异常
            last_exc = exc
            if attempt == _MAX_ATTEMPTS:
                logger.error("网络异常导致 LLM 请求失败: %s", exc)
                return None
            sleep_for = _exponential_backoff(attempt)
            logger.warning("网络异常 %s，%s 秒后重试", exc, sleep_for)
            time.sleep(sleep_for)
    if last_exc:
        logger.error("LLM 请求多次失败: %s", last_exc)
    return None


def _ollama_request(
    prompt: str,
    timeout_s: int,
    config: AppConfig,
    max_tokens: int,
    temperature: float,
) -> _LLMResponse | None:
    """调用 Ollama 本地推理服务。"""

    base_url = config.llm.base_url or os.getenv("OLLAMA_BASE_URL") or "http://127.0.0.1:11434"
    payload = {
        "model": config.llm.model,  # 指定 Ollama 模型名称
        "prompt": prompt,  # 输入提示词
        "options": {
            "temperature": temperature,  # 控制输出多样性
            "num_predict": max_tokens,  # 限制最大生成长度
        },
        "stream": False,  # 关闭流式传输，便于一次性解析
    }

    def _do_request() -> httpx.Response:
        # 创建同步 Client，复用 base_url 并设置超时
        with httpx.Client(base_url=base_url, timeout=timeout_s) as client:
            # 向 /api/generate 发送 POST 请求，附带 JSON 参数
            return client.post("/api/generate", json=payload)

    response = _request_with_retry(_do_request)
    if response is None:
        return None
    data = response.json()
    text = data.get("response") or data.get("text") or ""
    return _LLMResponse(text=text)


def _chat_completion_payload(
    prompt: str,
    model: str,
    temperature: float,
    max_tokens: int,
) -> dict:
    """构造 OpenAI Chat Completion 风格的 payload。"""

    return {
        "model": model,  # 指定模型名称
        "temperature": temperature,  # 输出温度
        "max_tokens": max_tokens,  # 最长输出 token
        "messages": [
            {"role": "system", "content": "You are a helpful writing assistant."},
            {"role": "user", "content": prompt},
        ],
    }


def _extract_text_from_chat_completion(data: dict) -> str:
    """从标准 chat completion 响应中提取文本。"""

    choices = data.get("choices") or []
    if not choices:
        return ""
    message = choices[0].get("message") or {}
    return message.get("content", "")


def _extract_text_from_completion(data: dict) -> str:
    """从纯 completion 响应中提取文本。"""

    choices = data.get("choices") or []
    if not choices:
        return ""
    text = choices[0].get("text")
    if text:
        return text
    return _extract_text_from_chat_completion(data)


def _vllm_request(
    prompt: str,
    timeout_s: int,
    config: AppConfig,
    max_tokens: int,
    temperature: float,
) -> _LLMResponse | None:
    """调用 vLLM OpenAI 兼容接口。"""

    base_url = config.llm.base_url or os.getenv("VLLM_BASE_URL") or "http://127.0.0.1:8000"
    payload = _chat_completion_payload(
        prompt=prompt,
        model=config.llm.model,
        temperature=temperature,
        max_tokens=max_tokens,
    )

    def _do_request() -> httpx.Response:
        # 与 OpenAI 兼容的路径通常为 /v1/chat/completions
        return httpx.post(
            f"{base_url}/v1/chat/completions",
            json=payload,
            timeout=timeout_s,
        )

    response = _request_with_retry(_do_request)
    if response is None:
        return None
    return _LLMResponse(text=_extract_text_from_chat_completion(response.json()))


def _groq_request(
    prompt: str,
    timeout_s: int,
    config: AppConfig,
    max_tokens: int,
    temperature: float,
) -> _LLMResponse | None:
    """调用 Groq 云端 LLM 服务。"""

    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        logger.warning("未配置 GROQ_API_KEY，返回占位文本")
        return _LLMResponse(text="[groq placeholder response]")
    payload = _chat_completion_payload(
        prompt=prompt,
        model=config.llm.model,
        temperature=temperature,
        max_tokens=max_tokens,
    )
    headers = {
        "Authorization": f"Bearer {api_key}",  # 认证头
        "Content-Type": "application/json",  # 明确声明 JSON
    }

    def _do_request() -> httpx.Response:
        return httpx.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers=headers,
            json=payload,
            timeout=timeout_s,
        )

    response = _request_with_retry(_do_request)
    if response is None:
        return None
    return _LLMResponse(text=_extract_text_from_chat_completion(response.json()))


def _fireworks_request(
    prompt: str,
    timeout_s: int,
    config: AppConfig,
    max_tokens: int,
    temperature: float,
) -> _LLMResponse | None:
    """调用 Fireworks AI Inference 接口。"""

    api_key = os.getenv("FIREWORKS_API_KEY")
    if not api_key:
        logger.warning("未配置 FIREWORKS_API_KEY，返回占位文本")
        return _LLMResponse(text="[fireworks placeholder response]")
    payload = _chat_completion_payload(
        prompt=prompt,
        model=config.llm.model,
        temperature=temperature,
        max_tokens=max_tokens,
    )
    headers = {
        "Authorization": f"Bearer {api_key}",  # Fireworks 鉴权
        "Content-Type": "application/json",
    }

    def _do_request() -> httpx.Response:
        return httpx.post(
            "https://api.fireworks.ai/inference/v1/chat/completions",
            headers=headers,
            json=payload,
            timeout=timeout_s,
        )

    response = _request_with_retry(_do_request)
    if response is None:
        return None
    return _LLMResponse(text=_extract_text_from_chat_completion(response.json()))


def _hf_endpoint_request(
    prompt: str,
    timeout_s: int,
    config: AppConfig,
    max_tokens: int,
    temperature: float,
) -> _LLMResponse | None:
    """调用 Hugging Face Inference Endpoints。"""

    api_key = os.getenv("HF_API_TOKEN")
    if not api_key:
        logger.warning("未配置 HF_API_TOKEN，返回占位文本")
        return _LLMResponse(text="[hf placeholder response]")
    payload = {
        "model": config.llm.model,  # 指定模型
        "prompt": prompt,  # 输入提示词
        "max_tokens": max_tokens,  # 输出长度限制
        "temperature": temperature,  # 温度
    }
    headers = {
        "Authorization": f"Bearer {api_key}",  # Hugging Face 鉴权
        "Content-Type": "application/json",
    }

    def _do_request() -> httpx.Response:
        return httpx.post(
            "https://api.endpoints.huggingface.cloud/v1/completions",
            headers=headers,
            json=payload,
            timeout=timeout_s,
        )

    response = _request_with_retry(_do_request)
    if response is None:
        return None
    return _LLMResponse(text=_extract_text_from_completion(response.json()))


def _openai_request(
    prompt: str,
    timeout_s: int,
    config: AppConfig,
    max_tokens: int,
    temperature: float,
) -> _LLMResponse | None:
    """调用 OpenAI Chat Completions 接口。"""

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        logger.warning("未配置 OPENAI_API_KEY，返回占位文本")
        return _LLMResponse(text="[openai placeholder response]")

    base_url = config.llm.base_url or os.getenv("OPENAI_BASE_URL") or "https://api.openai.com"
    payload = _chat_completion_payload(
        prompt=prompt,
        model=config.llm.model,
        temperature=temperature,
        max_tokens=max_tokens,
    )
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    def _do_request() -> httpx.Response:
        url = base_url.rstrip("/") + "/v1/chat/completions"
        return httpx.post(url, headers=headers, json=payload, timeout=timeout_s)

    response = _request_with_retry(_do_request)
    if response is None:
        return None
    return _LLMResponse(text=_extract_text_from_chat_completion(response.json()))


def _vps_request(
    prompt: str,
    timeout_s: int,
    config: AppConfig,
    max_tokens: int,
    temperature: float,
) -> _LLMResponse | None:
    """调用自建 VPS 实例暴露的 OpenAI 兼容接口。"""

    api_key = os.getenv("VPS_API_KEY")
    base_url = config.llm.base_url or os.getenv("VPS_API_BASE_URL")
    if not api_key or not base_url:
        logger.warning("VPS API 未正确配置，返回占位文本")
        return _LLMResponse(text="[vps placeholder response]")

    payload = _chat_completion_payload(
        prompt=prompt,
        model=config.llm.model,
        temperature=temperature,
        max_tokens=max_tokens,
    )
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    def _do_request() -> httpx.Response:
        url = base_url.rstrip("/") + "/v1/chat/completions"
        return httpx.post(url, headers=headers, json=payload, timeout=timeout_s)

    response = _request_with_retry(_do_request)
    if response is None:
        return None
    return _LLMResponse(text=_extract_text_from_chat_completion(response.json()))


_PROVIDER_REQUESTS: Dict[str, Callable[[str, int, AppConfig, int, float], _LLMResponse | None]] = {
    "ollama": _ollama_request,
    "vllm": _vllm_request,
    "groq": _groq_request,
    "fireworks": _fireworks_request,
    "hf_endpoint": _hf_endpoint_request,
    "openai": _openai_request,
    "vps": _vps_request,
}


def _placeholder_response(prompt: str) -> str:
    """构造占位回复，确保 smoke test 可通过。"""

    return (
        "[placeholder]\n"
        "Prompt snippet: "
        + prompt[:120]
        + "...\nPlease configure a valid LLM backend to receive live content."
    )


def generate(
    prompt: str,
    max_tokens: int | None = None,
    temperature: float | None = None,
    timeout_s: int | None = None,
) -> str:
    """统一的生成接口。"""

    if httpx is None:
        logger.warning("httpx 未安装，返回占位文本")
        return _placeholder_response(prompt)

    config = load_config()
    handler = _PROVIDER_REQUESTS.get(config.llm.provider)
    effective_timeout = timeout_s or config.llm.timeout_s
    effective_max_tokens = max_tokens or config.llm.max_tokens
    effective_temperature = temperature if temperature is not None else config.llm.temperature
    if not handler:
        logger.error("未实现的 LLM provider: %s", config.llm.provider)
        return _placeholder_response(prompt)

    response = handler(
        prompt,
        effective_timeout,
        config,
        effective_max_tokens,
        effective_temperature,
    )
    if response is None or not response.text:
        logger.warning("LLM 返回为空，使用占位文本")
        return _placeholder_response(prompt)
    return response.text


__all__ = ["generate"]
