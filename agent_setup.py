# ===== 引入区 =====
from typing import Any

from dotenv import load_dotenv
from pydantic import SecretStr
from langchain_deepseek import ChatDeepSeek
from langchain_ollama import ChatOllama
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.language_models import LanguageModelInput
from langchain.agents import create_agent

from logger import get_logger


# ===== 定义区 =====
class DeepSeekThinkingModel(ChatDeepSeek):
    def __init__(
        self,
        reasoning_effort: str = "high",
        enable_thinking: bool = True,
        **kwargs: Any,
    ):
        if enable_thinking:
            extra = kwargs.get("extra_body", {}) or {}
            extra["thinking"] = {"type": "enabled"}
            kwargs["extra_body"] = extra
        super().__init__(reasoning_effort=reasoning_effort, **kwargs)

    def _get_request_payload(
        self,
        input_: LanguageModelInput,
        *,
        stop: list[str] | None = None,
        **kwargs: Any,
    ) -> dict:
        messages = self._convert_input(input_).to_messages()
        payload = super()._get_request_payload(input_, stop=stop, **kwargs)
        for i, msg in enumerate(messages):
            if isinstance(msg, AIMessage) and "reasoning_content" in msg.additional_kwargs:
                if i < len(payload["messages"]):
                    payload["messages"][i]["reasoning_content"] = msg.additional_kwargs["reasoning_content"]
        return payload


def _build_deepseek_llm(
    api_key: str,
    model: str = "deepseek-v4-pro",
    reasoning_effort: str = "high",
    enable_thinking: bool = True,
    temperature: float = 0,
) -> DeepSeekThinkingModel | None:
    try:
        llm = DeepSeekThinkingModel(
            model=model,
            api_key=SecretStr(api_key),
            temperature=temperature,
            reasoning_effort=reasoning_effort,
            enable_thinking=enable_thinking,
        )
        logger.info(f"DeepSeek 模型初始化成功: {model}, reasoning_effort={reasoning_effort}")
        return llm
    except (ValueError, TypeError, OSError):
        logger.exception(f"DeepSeek 模型初始化失败: {model}")
        return None


def _build_ollama_llm(
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


def build_llm(
    provider: str = "deepseek",
    api_key: str | None = None,
    model: str | None = None,
    **kwargs: Any,
) -> BaseChatModel | None:
    if provider == "ollama":
        return _build_ollama_llm(
            model=model or "qwen3.5:4b",
            temperature=kwargs.get("temperature", 0),
            base_url=kwargs.get("base_url", "http://localhost:11434"),
            num_ctx=kwargs.get("num_ctx", 4096),
        )
    return _build_deepseek_llm(
        api_key=api_key or "",
        model=model or "deepseek-v4-pro",
        reasoning_effort=kwargs.get("reasoning_effort", "high"),
        enable_thinking=kwargs.get("enable_thinking", True),
        temperature=kwargs.get("temperature", 0),
    )


def build_agent(
    llm: BaseChatModel,
    tools: list,
    system_prompt: str = "你是一个会执行 shell 命令的助手。需要运行命令时调用 run_command 工具，根据需要选择 bash / powershell / nushell。",
) -> Any:
    try:
        agent = create_agent(model=llm, tools=tools, system_prompt=system_prompt)
        logger.info("Agent 创建成功")
        return agent
    except (ValueError, TypeError, AssertionError, OSError):
        logger.exception("Agent 创建失败")
        return None


# ===== 执行区 =====
logger = get_logger("agent_setup")

load_dotenv()
