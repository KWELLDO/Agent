# ===== 引入区 =====
import os
import threading
import traceback
from typing import Any, cast

from dotenv import load_dotenv
from langchain_core.messages import HumanMessage

from logger import setup_logging, get_logger
from model_setup import build_llm_from_env
from agent_setup import build_agent
from safety import MessageHistory
from tools import run_command
from scheduler import CronStore, SchedulerEngine, bind_engine, _CRON_MGMT_TOOLS


# ===== 定义区 =====
_CHAT_TIMEOUT = 180


class AgentManager:
    def __init__(self):
        self._lock = threading.Lock()
        self._llm = None
        self._agent = None
        self._history = None
        self._cron_store = None
        self._cron_engine = None
        self._ready = False
        self._error = None

        load_dotenv()
        setup_logging()
        self._logger = get_logger("agent_manager")

    def initialize(self) -> str | None:
        with self._lock:
            if self._ready:
                return None
            return self._initialize_unsafe()

    def _initialize_unsafe(self) -> str | None:
        try:
            self._logger.info("AgentManager 初始化中...")

            self._llm = build_llm_from_env()
            if self._llm is None:
                self._error = "LLM 初始化失败，请检查配置"
                return self._error

            cron_store_path = os.getenv("CRON_STORE_PATH", os.path.expanduser("~/.agent_cron_data.json"))
            self._cron_store = CronStore(file_path=cron_store_path)
            self._cron_engine = SchedulerEngine(self._cron_store)
            bind_engine(self._cron_engine)
            self._cron_engine.start()

            tools = [run_command] + _CRON_MGMT_TOOLS
            self._agent = build_agent(self._llm, tools)
            if self._agent is None:
                self._error = "Agent 创建失败"
                return self._error

            self._history = MessageHistory()
            self._ready = True
            self._logger.info("AgentManager 初始化完成")
            return None

        except Exception:
            self._error = f"初始化异常: {traceback.format_exc()}"
            self._logger.exception("AgentManager 初始化异常")
            return self._error

    @property
    def ready(self) -> bool:
        return self._ready

    @property
    def error(self) -> str | None:
        return self._error

    @property
    def cron_store(self):
        return self._cron_store

    @property
    def cron_engine(self):
        return self._cron_engine

    def chat(self, message: str) -> dict:
        if not self._ready:
            return {"error": "Agent 未就绪", "output": ""}

        with self._lock:
            try:
                messages = [*self._history.to_messages(), HumanMessage(content=message)]
                result = cast(dict[str, Any], self._agent.invoke(
                    cast(Any, {"messages": messages})
                ))
                self._history.reset(result["messages"])
                output = self._history.last().content

                self._logger.info(f"Chat ok: input={message[:60]}, output={str(output)[:60]}")
                return {"output": output, "error": None}

            except Exception:
                err = traceback.format_exc()
                self._logger.exception(f"Chat 异常: input={message[:60]}")
                return {"output": "", "error": err}

    def get_history(self) -> list[dict]:
        if not self._history:
            return []
        return [
            {"role": type(m).__name__.replace("Message", "").lower(), "content": m.content}
            for m in self._history.to_messages()
        ]

    def get_config(self) -> dict:
        return {
            "provider": os.getenv("LLM_PROVIDER", "deepseek"),
            "model": os.getenv("DEEPSEEK_MODEL", os.getenv("OLLAMA_MODEL", "unknown")),
            "cron_provider": os.getenv("CRON_LLM_PROVIDER", "ollama"),
            "cron_model": os.getenv("CRON_LLM_MODEL", "qwen3.5:4b"),
            "ready": self._ready,
            "error": self._error,
        }

    def shutdown(self) -> None:
        with self._lock:
            if self._cron_engine:
                try:
                    self._cron_engine.stop()
                except Exception:
                    pass
            self._ready = False
            self._logger.info("AgentManager 已关闭")


_manager: AgentManager | None = None
_manager_lock = threading.Lock()


def get_manager() -> AgentManager:
    global _manager
    if _manager is None:
        with _manager_lock:
            if _manager is None:
                _manager = AgentManager()
    return _manager


# ===== 执行区 =====
logger = get_logger("agent_manager_init")
