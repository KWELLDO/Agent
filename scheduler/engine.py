# ===== 引入区 =====
import os
import threading
import traceback
from datetime import datetime, timezone

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.events import EVENT_JOB_ERROR, EVENT_JOB_MISSED
from langchain_core.messages import HumanMessage

from scheduler.models import CronJob, ReportEntry, ScheduleType, _now_iso
from scheduler.store import CronStore
from scheduler.cron_agent import build_cron_agent

from logger import get_logger


# ===== 定义区 =====
_APS_JOB_PREFIX = "cron_"


class SchedulerEngine:
    def __init__(self, store: CronStore):
        self._store = store
        self._scheduler = BackgroundScheduler(daemon=True)
        self._running = False
        self._lock = threading.Lock()

        self._scheduler.add_listener(
            lambda e: logger.error(f"APScheduler 任务出错: {e}"),
            EVENT_JOB_ERROR | EVENT_JOB_MISSED,
        )

    # ── public API ──

    def start(self) -> None:
        with self._lock:
            if self._running:
                return
            self._register_all_jobs()
            self._scheduler.start()
            self._running = True
            logger.info("Cron 调度器已启动")

    def stop(self) -> None:
        with self._lock:
            if not self._running:
                return
            self._scheduler.shutdown(wait=False)
            self._running = False
            logger.info("Cron 调度器已停止")

    def add_job(self, job: CronJob) -> str | None:
        err = self._store.add_job(job)
        if err:
            return err
        if self._running and job.enabled:
            self._schedule_job(job)
        return None

    def remove_job(self, job_id: str) -> bool:
        ok = self._store.remove_job(job_id)
        if ok and self._running:
            try:
                self._scheduler.remove_job(_APS_JOB_PREFIX + job_id)
            except Exception:
                pass
        return ok

    def pause_job(self, job_id: str) -> bool:
        ok = self._store.update_job(job_id, enabled=False)
        if ok and self._running:
            try:
                self._scheduler.pause_job(_APS_JOB_PREFIX + job_id)
                logger.info(f"暂停定时任务: {job_id}")
            except Exception:
                pass
        return ok

    def resume_job(self, job_id: str) -> bool:
        ok = self._store.update_job(job_id, enabled=True)
        if ok and self._running:
            try:
                self._scheduler.resume_job(_APS_JOB_PREFIX + job_id)
                logger.info(f"恢复定时任务: {job_id}")
            except Exception:
                self._schedule_job(self._store.get_job(job_id))
        return ok

    def reload(self) -> None:
        if self._running:
            self._scheduler.remove_all_jobs()
            self._register_all_jobs()
            logger.info("Cron 调度器已重新加载")

    # ── internal ──

    def _register_all_jobs(self) -> None:
        for job in self._store.get_jobs():
            if job.enabled:
                self._schedule_job(job)

    def _schedule_job(self, job: CronJob) -> None:
        trigger = self._build_trigger(job)
        if trigger is None:
            logger.warning(f"无法为任务 {job.name} 构建触发器，跳过")
            return
        self._scheduler.add_job(
            func=self._execute_job_wrapper,
            trigger=trigger,
            args=[job.job_id],
            id=_APS_JOB_PREFIX + job.job_id,
            replace_existing=True,
            name=job.name,
            misfire_grace_time=300,
        )
        logger.info(f"已注册定时任务: {job.name} (type={job.schedule_type})")

    def _build_trigger(self, job: CronJob):
        try:
            if job.schedule_type == "cron" and job.cron_expr:
                return CronTrigger.from_crontab(job.cron_expr)
            elif job.schedule_type == "once" and job.run_at:
                dt = datetime.fromisoformat(job.run_at)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                return DateTrigger(run_date=dt)
            elif job.schedule_type == "interval" and job.interval_seconds:
                return IntervalTrigger(seconds=job.interval_seconds)
        except Exception:
            logger.exception(f"构建触发器失败: {job}")
            return None

    def _execute_job_wrapper(self, job_id: str) -> None:
        job = self._store.get_job(job_id)
        if job is None:
            logger.warning(f"任务 {job_id} 不存在但被触发")
            return

        logger.info(f"定时任务执行: {job.name} ({job.job_id})")
        agent = build_cron_agent(
            provider=job.llm_provider,
            model=job.llm_model,
        )
        if agent is None:
            output = f"[Cron 错误] LLM/Agent 构建失败 (provider={job.llm_provider}, model={job.llm_model})"
        else:
            try:
                result = agent.invoke({"messages": [HumanMessage(content=job.task_prompt)]})
                if isinstance(result, dict) and "messages" in result:
                    messages = result["messages"]
                    output = messages[-1].content if hasattr(messages[-1], "content") else str(messages[-1])
                else:
                    output = str(result)
            except Exception:
                logger.exception(f"定时任务执行异常: {job.name}")
                output = f"[Cron 错误] 执行异常\n{traceback.format_exc()}"

        report = ReportEntry(
            job_id=job.job_id,
            task_prompt=job.task_prompt,
            output=output,
        )
        self._store.add_report(report)
        self._store.update_job(job_id, last_run_at=_now_iso())
        if job.schedule_type == "once":
            self._store.update_job(job_id, enabled=False)
        logger.info(f"定时任务完成: {job.name}, 输出 {len(output)} 字符")


# ===== 执行区 =====
logger = get_logger("cron_engine")
