# ===== 引入区 =====
from logger import get_logger


# ===== 定义区 =====
class MessageHistory:
    def __init__(self, max_total: int = 60):
        self.max_total = max_total
        self._messages: list = []

    def append(self, msg) -> None:
        self._messages.append(msg)

    def reset(self, messages: list) -> None:
        self._messages = list(messages)
        self._trim()

    def last(self):
        if not self._messages:
            return None
        return self._messages[-1]

    def to_messages(self) -> list:
        return list(self._messages)

    def _trim(self) -> None:
        if len(self._messages) <= self.max_total:
            return
        removed = len(self._messages) - self.max_total
        logger.info(f"裁剪对话历史: {len(self._messages)} -> {self.max_total}")
        self._messages = self._messages[removed:]


# ===== 执行区 =====
logger = get_logger("history")
