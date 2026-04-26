#!/usr/bin/python3

import os
import sys
import logging
from typing import Any, cast
from dotenv import load_dotenv
from pydantic import SecretStr
from langchain_deepseek import ChatDeepSeek
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.language_models import LanguageModelInput
from langchain_core.tools import tool
from langchain.agents import create_agent


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

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("app.log", encoding="utf-8")
    ]
)
logger = logging.getLogger("main")

load_dotenv()

api_key = os.getenv("DEEPSEEK_API_KEY")
if not api_key:
    logger.error("未设置 DEEPSEEK_API_KEY 环境变量")
    sys.exit(1)

try:
    llm = DeepSeekThinkingModel(
        model="deepseek-v4-flash",
        api_key=SecretStr(api_key),
        temperature=0
    )
    logger.info("DeepSeek 模型初始化成功")
except (ValueError, TypeError, OSError):
    logger.exception("DeepSeek 模型初始化失败")
    sys.exit(1)


@tool
def get_weather(city: str) -> str:
    """查询指定城市的当前天气。参数 city 为城市名，如：北京、上海。"""
    logger.info(f"调用 get_weather 工具，参数 city={city}")
    return f"{city}：晴，25℃，微风。"


tools = [get_weather]

try:
    agent = create_agent(
        model=llm,
        tools=tools,
        system_prompt="你是一个会调用工具的助手。用户问天气时，调用 get_weather 工具。",
    )
    logger.info("Agent 创建成功")
except (ValueError, TypeError, AssertionError, OSError):
    logger.exception("Agent 创建失败")
    sys.exit(1)

if __name__ == "__main__":
    logger.info("应用启动")
    agent_state: dict[str, Any] = {"messages": []}
    print("输入问题（如：北京天气？），输入 exit 退出")
    while True:
        try:
            user_input = input("你：")
        except (EOFError, KeyboardInterrupt):
            logger.info("用户中断输入，退出")
            break
        except OSError:
            logger.exception("读取用户输入时出错")
            continue

        if user_input.lower() == "exit":
            logger.info("用户输入 exit，退出")
            break

        logger.info(f"用户输入: {user_input}")
        try:
            agent_state = cast(dict[str, Any], agent.invoke(
                cast(Any, {"messages": [*agent_state["messages"], HumanMessage(content=user_input)]})
            ))
            output = agent_state["messages"][-1].content
            logger.info(f"Agent 响应成功, output={output[:50]}")
            print("Agent：", output)
        except (KeyError, TypeError, ValueError):
            logger.exception(f"Agent 调用失败, input={user_input}")
            print("Agent：抱歉，处理请求时出现错误，请稍后再试。")

    logger.info("应用退出")