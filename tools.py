import subprocess

from langchain_core.tools import tool

from logger import get_logger

logger = get_logger("tools")

SHELL_CONFIG = {
    "bash":       {"executable": "/bin/bash",      "args": ["-c"]},
    "powershell": {"executable": "pwsh",            "args": ["-Command"]},
    "nushell":    {"executable": "nu",              "args": ["-c"]},
}


@tool
def run_command(command: str, shell: str = "bash") -> str:
    """执行 shell 命令并返回输出。支持 bash / powershell / nushell，后两者可用 to json 输出结构化数据。"""
    cfg = SHELL_CONFIG.get(shell)
    if cfg is None:
        return f"不支持的 shell: {shell}，可选: {', '.join(SHELL_CONFIG)}"

    logger.info(f"run_command: shell={shell}, command={command[:120]}")
    try:
        result = subprocess.run(
            [cfg["executable"], *cfg["args"], command],
            capture_output=True,
            text=True,
            timeout=30,
        )
    except FileNotFoundError:
        logger.error(f"{shell} 未安装")
        return f"{shell} 未安装，请先安装后再使用"
    except subprocess.TimeoutExpired:
        logger.warning(f"命令超时(30s): {command[:80]}")
        return "命令执行超时（30s）"
    except Exception:
        logger.exception(f"run_command 执行异常: {command[:80]}")
        return "执行命令时出错"

    if result.returncode != 0:
        logger.warning(f"命令退出码 {result.returncode}: {command[:80]}")
        return f"exit {result.returncode}\n{(result.stderr or result.stdout).strip()}"

    output = result.stdout.strip() or "(no output)"
    logger.info(f"run_command ok: {len(output)} chars")
    return output
