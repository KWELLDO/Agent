# ===== 引入区 =====
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Literal


# ===== 定义区 =====
ScheduleType = Literal["cron", "once", "interval"]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_id() -> str:
    return uuid.uuid4().hex[:12]


@dataclass
class CronJob:
    job_id: str = field(default_factory=_new_id)
    name: str = ""
    task_prompt: str = ""
    schedule_type: ScheduleType = "cron"
    cron_expr: str | None = None
    run_at: str | None = None
    interval_seconds: int | None = None
    enabled: bool = True
    llm_provider: str | None = None
    llm_model: str | None = None
    created_at: str = field(default_factory=_now_iso)
    last_run_at: str | None = None

    def validate(self) -> str | None:
        if not self.name.strip():
            return "任务名称不能为空"
        if not self.task_prompt.strip():
            return "任务 prompt 不能为空"
        if self.schedule_type == "cron" and not self.cron_expr:
            return "cron 类型必须提供 cron_expr"
        if self.schedule_type == "once" and not self.run_at:
            return "once 类型必须提供 run_at"
        if self.schedule_type == "interval":
            if self.interval_seconds is None or self.interval_seconds < 60:
                return "interval 至少 60 秒"
        return None


@dataclass
class ReportEntry:
    report_id: str = field(default_factory=_new_id)
    job_id: str = ""
    triggered_at: str = field(default_factory=_now_iso)
    task_prompt: str = ""
    output: str = ""
    read: bool = False
    conversation: list[dict] = field(default_factory=list)

    def summary(self, max_len: int = 80) -> str:
        text = self.output.replace("\n", " ").strip()
        if len(text) > max_len:
            return text[:max_len] + "..."
        return text or "(空输出)"

    def to_conversation_msg(self, role: str, content: str) -> dict:
        return {"role": role, "content": content, "time": _now_iso()}
