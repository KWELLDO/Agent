# ===== 引入区 =====
import os
import signal
import threading
import time

from shell_tool.session import SHELL_CONFIG, ShellSession
from safety.cleanup import register

from logger import get_logger


# ===== 定义区 =====
class _PoolItem:
    def __init__(self, session: ShellSession, shell: str):
        self.session = session
        self.shell = shell
        self.last_used = time.time()


class SafetySessionPool:
    def __init__(self, max_sessions: int = 3, idle_timeout: int = 300):
        self.max_sessions = max_sessions
        self.idle_timeout = idle_timeout
        self._pool: dict[str, _PoolItem] = {}
        self._locks: dict[str, threading.Lock] = {}
        self._evict_lock = threading.Lock()
        register(self.close_all)

    def acquire(self, shell: str = "bash") -> ShellSession:
        lock = self._locks.setdefault(shell, threading.Lock())
        lock.acquire()
        return self._get_or_create(shell)

    def release(self, shell: str = "bash") -> None:
        lock = self._locks.get(shell)
        if lock and lock.locked():
            lock.release()

    def get(self, shell: str = "bash") -> ShellSession:
        return self._get_or_create(shell)

    def _get_or_create(self, shell: str = "bash") -> ShellSession:
        item = self._pool.get(shell)

        if item is not None:
            try:
                alive = item.session.child.isalive()
            except Exception:
                alive = False
            if not alive:
                logger.info(f"会话 {shell} 重建中（上次已断开或无 PTY）")
                try:
                    item.session.close()
                except Exception:
                    pass
                del self._pool[shell]
            else:
                item.last_used = time.time()
                return item.session

        with self._evict_lock:
            self._evict_if_full()
        try:
            session = ShellSession(shell)
        except Exception as e:
            logger.error(f"创建 {shell} 会话失败: {e}")
            raise
        self._pool[shell] = _PoolItem(session, shell)
        return session

    def kill(self, shell: str = "bash") -> None:
        item = self._pool.get(shell)
        if item is not None and item.session.child.isalive():
            pid = item.session.child.pid
            logger.warning(f"强制终止会话 {shell} (pid={pid})")
            try:
                os.kill(pid, signal.SIGKILL)
            except OSError:
                pass
            item.session.close()
            del self._pool[shell]

    def close_all(self) -> None:
        for shell, item in list(self._pool.items()):
            logger.info(f"关闭会话: {shell}")
            item.session.close()
        self._pool.clear()

    def _evict_if_full(self) -> None:
        now = time.time()

        for shell, item in list(self._pool.items()):
            if now - item.last_used > self.idle_timeout:
                logger.info(f"会话 {shell} 空闲超时({self.idle_timeout}s)，关闭")
                item.session.close()
                del self._pool[shell]

        while len(self._pool) >= self.max_sessions:
            oldest = min(self._pool.items(), key=lambda x: x[1].last_used)
            logger.info(f"会话 {oldest[0]} 被 LRU 淘汰")
            oldest[1].session.close()
            del self._pool[oldest[0]]


pool = SafetySessionPool()


# ===== 执行区 =====
logger = get_logger("session_pool")
