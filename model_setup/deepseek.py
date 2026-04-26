# ===== 引入区 =====
from typing import Any

from pydantic import SecretStr
from langchain_deepseek import ChatDeepSeek
from langchain_core.messages import AIMessage
from langchain_core.language_models import LanguageModelInput

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


def build_deepseek_llm(
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


# ===== 执行区 =====
logger = get_logger("model_deepseek")
