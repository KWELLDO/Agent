# ===== 引入区 =====
from typing import Any

from dotenv import load_dotenv
from langchain_core.language_models import BaseChatModel
from langchain.agents import create_agent

from logger import get_logger


# ===== 定义区 =====
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
