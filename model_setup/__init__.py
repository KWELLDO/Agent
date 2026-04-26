# ===== 引入区 =====
from typing import Any

from langchain_core.language_models import BaseChatModel

from model_setup.deepseek import build_deepseek_llm
from model_setup.ollama import build_ollama_llm

from logger import get_logger


# ===== 定义区 =====
def build_llm(
    provider: str = "deepseek",
    api_key: str | None = None,
    model: str | None = None,
    **kwargs: Any,
) -> BaseChatModel | None:
    if provider == "ollama":
        return build_ollama_llm(
            model=model or "qwen3.5:4b",
            temperature=kwargs.get("temperature", 0),
            base_url=kwargs.get("base_url", "http://localhost:11434"),
            num_ctx=kwargs.get("num_ctx", 4096),
        )
    return build_deepseek_llm(
        api_key=api_key or "",
        model=model or "deepseek-v4-pro",
        reasoning_effort=kwargs.get("reasoning_effort", "high"),
        enable_thinking=kwargs.get("enable_thinking", True),
        temperature=kwargs.get("temperature", 0),
    )


__all__ = ["build_llm", "build_deepseek_llm", "build_ollama_llm"]


# ===== 执行区 =====
logger = get_logger("model_setup")
