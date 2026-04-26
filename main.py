#!/usr/bin/python3

# ===== 引入区 =====
import os
import sys
from typing import Any, cast

from langchain_core.messages import HumanMessage

from logger import setup_logging, get_logger
from tools import run_command
from model_setup import build_llm_from_env
from agent_setup import build_agent
from safety import MessageHistory
from scheduler import CronStore, SchedulerEngine, bind_engine, _CRON_MGMT_TOOLS, run_report_session


# ===== 执行区 =====
setup_logging()
logger = get_logger("main")

llm = build_llm_from_env()
if llm is None:
    sys.exit(1)

# ── 初始化 Cron 调度器 ──
cron_store_path = os.getenv("CRON_STORE_PATH", os.path.expanduser("~/.agent_cron_data.json"))
cron_store = CronStore(file_path=cron_store_path)
cron_engine = SchedulerEngine(cron_store)
bind_engine(cron_engine)
cron_engine.start()

tools = [run_command] + _CRON_MGMT_TOOLS

agent = build_agent(llm, tools)
if agent is None:
    sys.exit(1)

if __name__ == "__main__":
    logger.info("应用启动")
    history = MessageHistory()
    print("本项目是Agent项目，输入 exit 退出，输入 cron 查看定时任务报告")
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

        if user_input.lower() == "cron":
            logger.info("用户进入 Cron 报告会话")
            run_report_session(cron_store)
            continue

        logger.info(f"用户输入: {user_input}")
        try:
            result = cast(dict[str, Any], agent.invoke(
                cast(Any, {"messages": [*history.to_messages(), HumanMessage(content=user_input)]})
            ))
            history.reset(result["messages"])
            output = history.last().content
            logger.info(f"Agent 响应成功, output={output[:50]}")
            print("Agent：", output)
        except (KeyError, TypeError, ValueError):
            logger.exception(f"Agent 调用失败, input={user_input}")
            print("Agent：抱歉，处理请求时出现错误，请稍后再试。")

    cron_engine.stop()
    logger.info("应用退出")
