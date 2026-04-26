#!/usr/bin/python3

# ===== 引入区 =====
import sys
from typing import Any, cast

from langchain_core.messages import HumanMessage

from logger import setup_logging, get_logger
from tools import run_command
from model_setup import build_llm_from_env
from agent_setup import build_agent


# ===== 执行区 =====
setup_logging()
logger = get_logger("main")

llm = build_llm_from_env()
if llm is None:
    sys.exit(1)

tools = [run_command]

agent = build_agent(llm, tools)
if agent is None:
    sys.exit(1)

if __name__ == "__main__":
    logger.info("应用启动")
    agent_state: dict[str, Any] = {"messages": []}
    print("本项目是Agent项目，输入 exit 退出")
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
