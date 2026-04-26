# ===== 引入区 =====
from langchain_ollama import ChatOllama

from logger import get_logger


# ===== 定义区 =====
def build_ollama_llm(
    model: str = "qwen3.5:4b",
    temperature: float = 0,
    base_url: str = "http://localhost:11434",
    num_ctx: int = 4096,
) -> ChatOllama | None:
    try:
        llm = ChatOllama(
            model=model,
            temperature=temperature,
            base_url=base_url,
            num_ctx=num_ctx,
        )
        logger.info(f"Ollama 模型初始化成功: {model}")
        return llm
    except Exception:
        logger.exception(f"Ollama 模型初始化失败: {model}")
        return None


# ===== 执行区 =====
logger = get_logger("model_ollama")
