# ===== 引入区 =====
import atexit
import signal
import sys

from logger import get_logger


# ===== 定义区 =====
_cleanups: list = []


def register(func) -> None:
    _cleanups.append(func)


def cleanup_all() -> None:
    for func in _cleanups:
        try:
            func()
        except Exception:
            pass


def _signal_handler(signum, frame):
    logger.warning(f"收到信号 {signum}，清理资源中")
    cleanup_all()
    sys.exit(128 + signum)


# 自动注册到 Python 退出和系统信号
atexit.register(cleanup_all)
signal.signal(signal.SIGINT, _signal_handler)
signal.signal(signal.SIGTERM, _signal_handler)


# ===== 执行区 =====
logger = get_logger("cleanup")
