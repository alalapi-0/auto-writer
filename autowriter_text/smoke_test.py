"""快速验证多后端 LLM 客户端的占位能力。"""

from __future__ import annotations

from autowriter_text.generator.llm_client import generate


def main() -> None:
    """打印一段占位响应或真实模型输出。"""

    prompt = "请简述 AutoWriter 的设计目标。"
    result = generate(prompt)
    print(result)


if __name__ == "__main__":
    main()
