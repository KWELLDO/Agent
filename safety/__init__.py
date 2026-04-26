# ===== 引入区 =====
import safety.cleanup  # import 即生效：注册 atexit + signal

from safety.history import MessageHistory


__all__ = ["MessageHistory"]
