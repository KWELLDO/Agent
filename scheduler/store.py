# ===== 引入区 =====
import json
import os
import threading
from pathlib import Path

from scheduler.models import CronJob, ReportEntry

from logger import get_logger


# ===== 定义区 =====
DEFAULT_STORE_PATH = os.path.expanduser("~/.agent_cron_data.json")
MAX_REPORTS = 100
MAX_JOBS = 50


class CronStore:
    def __init__(self, file_path: str = DEFAULT_STORE_PATH):
        self._path = file_path
        self._lock = threading.Lock()
        self._jobs: list[CronJob] = []
        self._reports: list[ReportEntry] = []
        self._load()

    # ── jobs ──

    def get_jobs(self) -> list[CronJob]:
        with self._lock:
            return list(self._jobs)

    def get_job(self, job_id: str) -> CronJob | None:
        with self._lock:
            for j in self._jobs:
                if j.job_id == job_id:
                    return j
            return None

    def add_job(self, job: CronJob) -> str | None:
        err = job.validate()
        if err:
            return err
        with self._lock:
            if len(self._jobs) >= MAX_JOBS:
                return f"任务数量已达上限({MAX_JOBS})"
            for j in self._jobs:
                if j.name == job.name:
                    return f"任务名称已存在: {job.name}"
            self._jobs.append(job)
            self._save()
            logger.info(f"新增定时任务: {job.name} ({job.job_id})")
            return None

    def remove_job(self, job_id: str) -> bool:
        with self._lock:
            before = len(self._jobs)
            self._jobs = [j for j in self._jobs if j.job_id != job_id]
            if len(self._jobs) == before:
                return False
            self._save()
            logger.info(f"删除定时任务: {job_id}")
            return True

    def update_job(self, job_id: str, **kwargs) -> bool:
        with self._lock:
            for j in self._jobs:
                if j.job_id == job_id:
                    for k, v in kwargs.items():
                        if hasattr(j, k):
                            setattr(j, k, v)
                    self._save()
                    return True
            return False

    # ── reports ──

    def add_report(self, report: ReportEntry) -> None:
        with self._lock:
            self._reports.append(report)
            if len(self._reports) > MAX_REPORTS:
                self._reports = self._reports[-MAX_REPORTS:]
            self._save()

    def get_unread_reports(self) -> list[ReportEntry]:
        with self._lock:
            return [r for r in self._reports if not r.read]

    def get_all_reports(self, limit: int = 20) -> list[ReportEntry]:
        with self._lock:
            return self._reports[-limit:]

    def get_report(self, report_id: str) -> ReportEntry | None:
        with self._lock:
            for r in self._reports:
                if r.report_id == report_id:
                    return r
            return None

    def mark_report_read(self, report_id: str) -> bool:
        with self._lock:
            for r in self._reports:
                if r.report_id == report_id:
                    r.read = True
                    self._save()
                    return True
            return False

    def append_report_conversation(self, report_id: str, msg: dict) -> bool:
        with self._lock:
            for r in self._reports:
                if r.report_id == report_id:
                    r.conversation.append(msg)
                    self._save()
                    return True
            return False

    def get_job_reports(self, job_id: str, limit: int = 10) -> list[ReportEntry]:
        with self._lock:
            return [r for r in self._reports if r.job_id == job_id][-limit:]

    # ── persistence ──

    def _load(self) -> None:
        try:
            if not os.path.exists(self._path):
                logger.info(f"Cron 存储文件不存在，将创建: {self._path}")
                return
            with open(self._path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self._jobs = [CronJob(**j) for j in data.get("jobs", [])]
            self._reports = [ReportEntry(**r) for r in data.get("reports", [])]
            logger.info(f"已加载 {len(self._jobs)} 个定时任务, {len(self._reports)} 条报告")
        except (json.JSONDecodeError, OSError, TypeError):
            logger.exception(f"Cron 存储文件损坏，使用空数据: {self._path}")
            self._jobs = []
            self._reports = []

    def _save(self) -> None:
        data = {
            "version": 1,
            "jobs": [j.__dict__ for j in self._jobs],
            "reports": [r.__dict__ for r in self._reports],
        }
        tmp = self._path + ".tmp"
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            os.replace(tmp, self._path)
        except OSError:
            logger.exception(f"Cron 存储写入失败: {self._path}")


# ===== 执行区 =====
logger = get_logger("cron_store")
