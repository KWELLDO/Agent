# ===== 引入区 =====
import os
import threading

from langchain_core.tools import tool

from shell_tool.session import SHELL_CONFIG
from shell_tool.safety_session_pool import SafetySessionPool
from shell_tool.tool import MAX_OUTPUT_CHARS
from model_setup import build_llm
from agent_setup import build_agent

from logger import get_logger


# ===== 定义区 =====
_cron_pool = SafetySessionPool(max_sessions=2, idle_timeout=120)
_cron_pool_lock = threading.Lock()


def _cron_pool_get(shell: str):
    with _cron_pool_lock:
        return _cron_pool.get(shell)


def _cron_pool_kill(shell: str):
    with _cron_pool_lock:
        _cron_pool.kill(shell)


@tool
def _cron_run_command(command: str, shell: str = "bash", cwd: str | None = None, timeout: int = 30) -> str:
    """在独立的 shell 会话中执行命令（cron 任务专用，与主会话隔离）。

    Args:
        command: 要执行的命令
        shell: 使用的 shell (bash / powershell / nushell)
        cwd: 执行目录，为 None 时保持在当前会话目录
        timeout: 超时秒数
    """
    if shell not in SHELL_CONFIG:
        return f"不支持的 shell: {shell}，可选: {', '.join(SHELL_CONFIG)}"

    if cwd is not None and str(cwd).lower() in ("none", "null", ""):
        cwd = None

    try:
        session = _cron_pool_get(shell)
        output = session.execute(command, cwd=cwd, timeout=timeout)
    except FileNotFoundError:
        return f"{shell} 未安装，请先安装后再使用"
    except TimeoutError:
        logger.warning(f"Cron 命令超时({timeout}s): {command[:80]}")
        _cron_pool_kill(shell)
        return f"命令执行超时（{timeout}s）"
    except Exception:
        logger.exception(f"Cron 命令异常: {command[:80]}")
        return "执行命令时出错"

    if len(output) > MAX_OUTPUT_CHARS:
        output = output[:MAX_OUTPUT_CHARS] + f"\n...（截断了 {len(output) - MAX_OUTPUT_CHARS} 字符）"
    return output


_CRON_TOOLS = [_cron_run_command]


def build_cron_agent(
    provider: str | None = None,
    model: str | None = None,
    api_key: str | None = None,
    reasoning_effort: str = "high",
    base_url: str | None = None,
    num_ctx: int = 4096,
    temperature: float = 0,
    system_prompt: str | None = None,
):
    if system_prompt is None:
        system_prompt = "你是一个执行定时任务的自动化助手。根据任务描述执行必要的 shell 命令并汇报结果。"

    if provider is None:
        provider = os.getenv("CRON_LLM_PROVIDER", "ollama")
    if model is None:
        model = os.getenv("CRON_LLM_MODEL", "qwen3.5:4b")
    if api_key is None:
        api_key = os.getenv("DEEPSEEK_API_KEY", "")
    if base_url is None:
        base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    num_ctx = int(os.getenv("OLLAMA_NUM_CTX", str(num_ctx)))
    if provider == "deepseek":
        reasoning_effort = os.getenv("DEEPSEEK_REASONING_EFFORT", reasoning_effort)

    llm = build_llm(
        provider=provider,
        model=model,
        api_key=api_key,
        reasoning_effort=reasoning_effort,
        base_url=base_url,
        num_ctx=num_ctx,
        temperature=temperature,
        enable_thinking=provider == "deepseek",
    )
    if llm is None:
        logger.error(f"Cron Agent LLM 构建失败: provider={provider}, model={model}")
        return None

    agent = build_agent(llm, _CRON_TOOLS, system_prompt=system_prompt)
    if agent is None:
        logger.error("Cron Agent 构建失败")
        return None

    return agent


# ===== 执行区 =====
logger = get_logger("cron_agent")
