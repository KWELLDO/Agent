# ===== 引入区 =====
import os
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


def build_llm_from_env() -> BaseChatModel | None:
    """从环境变量读取 LLM 配置并初始化模型。

    读取的环境变量:
      LLM_PROVIDER            deepseek / ollama（默认 deepseek）
      DEEPSEEK_API_KEY        DeepSeek API 密钥
      DEEPSEEK_MODEL          模型名（默认 deepseek-v4-pro）
      DEEPSEEK_REASONING_EFFORT 思考强度（默认 high）
      OLLAMA_MODEL            本地模型名（默认 qwen3.5:4b）
      OLLAMA_BASE_URL         服务地址（默认 http://localhost:11434）
      OLLAMA_NUM_CTX          上下文长度（默认 4096）
    """
    provider = os.getenv("LLM_PROVIDER", "deepseek").lower()

    if provider == "ollama":
        logger.info(f"LLM 配置: provider=ollama, model={os.getenv('OLLAMA_MODEL', 'qwen3.5:4b')}")
        return build_ollama_llm(
            model=os.getenv("OLLAMA_MODEL", "qwen3.5:4b"),
            temperature=0,
            base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"),
            num_ctx=int(os.getenv("OLLAMA_NUM_CTX", "4096")),
        )

    api_key = os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        logger.error("DEEPSEEK_API_KEY 未设置。如需使用本地模型，请设置 LLM_PROVIDER=ollama")
        return None

    model = os.getenv("DEEPSEEK_MODEL", "deepseek-v4-pro")
    effort = os.getenv("DEEPSEEK_REASONING_EFFORT", "high")
    logger.info(f"LLM 配置: provider=deepseek, model={model}, reasoning_effort={effort}")
    return build_deepseek_llm(
        api_key=api_key,
        model=model,
        reasoning_effort=effort,
        temperature=0,
    )


__all__ = ["build_llm", "build_llm_from_env", "build_deepseek_llm", "build_ollama_llm"]


# ===== 执行区 =====
logger = get_logger("model_setup")
