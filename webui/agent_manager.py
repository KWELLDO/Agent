# ===== 引入区 =====
import os
import threading
import traceback
from typing import Any, AsyncGenerator, cast

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

    async def chat_stream(self, message: str) -> AsyncGenerator[dict, None]:
        if not self._ready:
            yield {"type": "error", "content": "Agent 未就绪"}
            return

        try:
            messages = [*self._history.to_messages(), HumanMessage(content=message)]
            full_content = ""
            final_messages = None

            async for event in self._agent.astream(
                {"messages": messages},
                stream_mode=["messages", "updates"],
                config={"recursion_limit": 30},
            ):
                mode = event[0]
                data = event[1]

                if mode == "messages":
                    msg_chunk, metadata = data
                    node = metadata.get("langgraph_node", "")

                    if node in ("model", "agent"):
                        tcc = getattr(msg_chunk, "tool_call_chunks", None)
                        if tcc:
                            for tc in tcc:
                                name = getattr(tc, "name", None) or getattr(tc, "id", None)
                                if name:
                                    yield {"type": "tool_call", "content": f"调用工具: {name}"}

                        if msg_chunk.content:
                            full_content += msg_chunk.content
                            yield {"type": "token", "content": msg_chunk.content}

                    elif node == "tools":
                        if hasattr(msg_chunk, "content") and msg_chunk.content:
                            yield {"type": "tool_result", "content": str(msg_chunk.content)[:500]}

                elif mode == "updates":
                    for node_name, node_data in data.items():
                        if "messages" in node_data:
                            final_messages = node_data["messages"]
                            msgs = node_data["messages"]
                            if node_name in ("model", "agent") and msgs:
                                last = msgs[-1]
                                tcs = getattr(last, "tool_calls", None)
                                if tcs:
                                    for tc in tcs:
                                        name = tc.get("name") or tc.get("id", "")
                                        args = tc.get("args", {}) if isinstance(tc.get("args"), dict) else {}
                                        yield {"type": "tool_call", "content": f"调用工具: {name}({args})"}

            if final_messages:
                self._history.reset(list(final_messages))
            yield {"type": "done", "content": full_content}

        except Exception:
            err = traceback.format_exc()
            self._logger.exception(f"Chat 流异常: input={message[:60]}")
            yield {"type": "error", "content": err}

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
