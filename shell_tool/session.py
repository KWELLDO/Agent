import re
import shlex

import pexpect

from logger import get_logger

logger = get_logger("shell_session")

SHELL_CONFIG = {
    "bash":       {"executable": "/bin/bash"},
    "powershell": {"executable": "pwsh"},
    "nushell":    {"executable": "nu"},
}

_MARKER = "###CMD_DONE###"
# 只匹配新行开头的 MARKER，避免匹配到回显的命令行（如 echo '###CMD_DONE###'）
_MARKER_RE = re.compile(f"\n{_MARKER}")


class ShellSession:
    def __init__(self, shell: str = "bash"):
        cfg = SHELL_CONFIG.get(shell)
        if cfg is None:
            raise ValueError(f"不支持的 shell: {shell}")

        logger.info(f"启动持久 shell 会话: {shell}")
        self.child = pexpect.spawn(
            cfg["executable"],
            encoding="utf-8",
            codec_errors="replace",
            timeout=30,
            env={"TERM": "dumb"},
        )
        self._cwd = "."
        self.shell = shell
        # 排空 spawn 后的所有初始输出
        self.child.sendline(f"echo '{_MARKER}'")
        self.child.expect(_MARKER_RE, timeout=10)

    def execute(self, command: str, cwd: str | None = None, timeout: int = 30) -> str:
        self.child.timeout = timeout

        if cwd is not None and cwd != self._cwd:
            logger.info(f"切换目录: {self._cwd} -> {cwd}")
            self.child.sendline(f"cd {shlex.quote(cwd)} && echo '{_MARKER}'")
            self.child.expect(_MARKER_RE, timeout=timeout)
            self._cwd = cwd

        self.child.sendline(f"{command} 2>&1; echo '{_MARKER}'")
        self.child.expect(_MARKER_RE, timeout=timeout)
        output = (self.child.before or "").strip()
        # 去掉第一行（被回显的命令本身），有真实输出时才有第二行
        if "\n" in output:
            output = output.split("\n", 1)[1].strip()
        else:
            output = ""
        return output or "(no output)"

    def close(self):
        if self.child and self.child.isalive():
            logger.info(f"关闭 shell 会话: {self.shell}")
            self.child.close()


_session_cache: dict[str, ShellSession] = {}


def get_session(shell: str = "bash") -> ShellSession:
    if shell not in _session_cache:
        _session_cache[shell] = ShellSession(shell)
    return _session_cache[shell]
