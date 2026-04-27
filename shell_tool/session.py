# ===== 引入区 =====
import re
import shlex
import subprocess
import time

import pexpect

from logger import get_logger


# ===== 定义区 =====
SHELL_CONFIG = {
    "bash":    {"executable": "/bin/bash"},
    "nushell": {"executable": "nu"},
}

_MARKER = "###CMD_DONE###"
_MARKER_RE = re.compile(f"\n{_MARKER}")


class ShellSession:
    def __init__(self, shell: str = "bash"):
        cfg = SHELL_CONFIG.get(shell)
        if cfg is None:
            raise ValueError(f"不支持的 shell: {shell}")

        self._shell = shell

        # nushell 不用 PTY，用 subprocess 临时执行
        if shell == "nushell":
            logger.info("nushell 使用 subprocess 模式")
            self.child = None
            self._cwd = "."
            return

        _PAGER_ENV = {
            "TERM": "dumb",
            "PAGER": "cat",
            "GIT_PAGER": "cat",
            "MANPAGER": "cat",
            "SYSTEMD_PAGER": "cat",
            "BROWSER": "echo",
            "LANG": "C.UTF-8",
            "PAGER_DISABLE": "1",
            "MORE": "-R",
        }
        logger.info(f"启动持久 shell 会话: {shell}")
        self.child = pexpect.spawn(
            cfg["executable"],
            encoding="utf-8",
            codec_errors="replace",
            timeout=30,
            maxread=65536,
            searchwindowsize=None,
            env=_PAGER_ENV,
        )
        self._cwd = "."
        self.child.sendline(f"echo '{_MARKER}'")
        self.child.expect(_MARKER_RE, timeout=10)

    def execute(self, command: str, cwd: str | None = None, timeout: int = 30) -> str:
        # nushell: 每次启动临时进程执行，cd 靠 cwd 参数
        if self._shell == "nushell":
            try:
                result = subprocess.run(
                    ["nu", "-c", command],
                    capture_output=True, text=True,
                    cwd=cwd or self._cwd,
                    timeout=timeout,
                )
                out = (result.stdout + result.stderr).strip()
                return out or "(no output)"
            except subprocess.TimeoutExpired:
                return "(超时)"
            except Exception as e:
                return f"[错误] {e}"

        # bash: use PTY
        self.child.timeout = timeout

        if cwd is not None and cwd != self._cwd:
            logger.info(f"切换目录: {self._cwd} -> {cwd}")
            self.child.sendline(f"cd {shlex.quote(cwd)} && echo '{_MARKER}'")
            self.child.expect(_MARKER_RE, timeout=timeout)
            self._cwd = cwd

        self.child.sendline(f"{command} 2>&1; echo '{_MARKER}'")
        self.child.expect(_MARKER_RE, timeout=timeout)
        output = (self.child.before or "").strip()
        if "\n" in output:
            output = output.split("\n", 1)[1].strip()
        else:
            output = ""

        self.child.buffer = ""
        return output or "(no output)"

    def close(self):
        if self._shell == "nushell":
            return
        if self.child and self.child.isalive():
            logger.info(f"关闭 shell 会话: {self._shell}")
            self.child.close()


# ===== 执行区 =====
logger = get_logger("shell_session")
