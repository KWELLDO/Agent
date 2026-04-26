# ===== 引入区 =====
from langchain_core.tools import tool

from shell_tool.session import SHELL_CONFIG
from shell_tool.safety_session_pool import pool
from logger import get_logger


# ===== 定义区 =====
MAX_OUTPUT_CHARS = 4000


@tool
def run_command(command: str, shell: str = "bash", cwd: str | None = None, timeout: int = 30) -> str:
    """在持久 shell 会话中执行命令并返回输出。

    会话会保持 cd、export、source venv 等状态。
    支持 bash / powershell / nushell，后两者可用 to json 输出结构化数据。

    Args:
        command: 要执行的命令
        shell: 使用的 shell (bash / powershell / nushell)
        cwd: 执行目录，为 None 时保持在当前会话目录
        timeout: 超时秒数
    """
    if shell not in SHELL_CONFIG:
        return f"不支持的 shell: {shell}，可选: {', '.join(SHELL_CONFIG)}"

    logger.info(f"run_command: shell={shell}, cwd={cwd}, timeout={timeout}, command={command[:120]}")
    try:
        session = pool.get(shell)
        output = session.execute(command, cwd=cwd, timeout=timeout)
    except FileNotFoundError:
        logger.error(f"{shell} 未安装")
        return f"{shell} 未安装，请先安装后再使用"
    except TimeoutError:
        logger.warning(f"命令超时({timeout}s)，强制终止: {command[:80]}")
        pool.kill(shell)
        return f"命令执行超时（{timeout}s）"
    except Exception:
        logger.exception(f"run_command 执行异常: {command[:80]}")
        return "执行命令时出错"

    if len(output) > MAX_OUTPUT_CHARS:
        logger.info(f"输出截断: {len(output)} -> {MAX_OUTPUT_CHARS} chars")
        output = output[:MAX_OUTPUT_CHARS] + f"\n...（截断了 {len(output) - MAX_OUTPUT_CHARS} 字符）"

    logger.info(f"run_command ok: {len(output)} chars")
    return output


# ===== 执行区 =====
logger = get_logger("shell_tool")
