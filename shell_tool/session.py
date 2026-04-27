# ===== 引入区 =====
import re
import shlex
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

    def _and_marker(self, command: str) -> str:
        if self._shell == "nushell":
            return f"{command}; echo '{_MARKER}'"
        return f"{command} 2>&1; echo '{_MARKER}'"

    def _cd_marker(self, path: str) -> str:
        if self._shell == "nushell":
            return f"cd {shlex.quote(path)}; echo '{_MARKER}'"
        return f"cd {shlex.quote(path)} && echo '{_MARKER}'"

    def execute(self, command: str, cwd: str | None = None, timeout: int = 30) -> str:
        self.child.timeout = timeout

        if cwd is not None and cwd != self._cwd:
            logger.info(f"切换目录: {self._cwd} -> {cwd}")
            self.child.sendline(self._cd_marker(cwd))
            self.child.expect(_MARKER_RE, timeout=timeout)
            self._cwd = cwd

        self.child.sendline(self._and_marker(command))
        self.child.expect(_MARKER_RE, timeout=timeout)
        output = (self.child.before or "").strip()
        if "\n" in output:
            output = output.split("\n", 1)[1].strip()
        else:
            output = ""

        self.child.buffer = ""
        return output or "(no output)"

    def close(self):
        if self.child and self.child.isalive():
            logger.info(f"关闭 shell 会话: {self._shell}")
            self.child.close()


# ===== 执行区 =====
logger = get_logger("shell_session")
