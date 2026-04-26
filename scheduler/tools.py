# ===== 引入区 =====
from langchain_core.tools import tool

from scheduler.models import CronJob, _now_iso

from logger import get_logger


# ===== 定义区 =====
_engine_ref = None


def bind_engine(engine) -> None:
    global _engine_ref
    _engine_ref = engine


@tool
def add_cron_job(
    name: str,
    task_prompt: str,
    schedule_type: str = "cron",
    cron_expr: str | None = None,
    run_at: str | None = None,
    interval_seconds: int | None = None,
    llm_provider: str | None = None,
    llm_model: str | None = None,
) -> str:
    """注册一个定时任务。支持三种调度类型：

    - cron: 按 cron 表达式周期执行（如 "0 9 * * *" 每天早 9 点）
    - once: 一次性定时任务，在指定时间执行一次
    - interval: 按固定间隔执行（最少 60 秒）

    Args:
        name: 任务名称（唯一标识）
        task_prompt: 任务触发时发给 agent 的指令描述
        schedule_type: 调度类型 "cron" / "once" / "interval"
        cron_expr: cron 表达式（schedule_type="cron" 时必填）
        run_at: 执行时间 ISO 格式（schedule_type="once" 时必填）
        interval_seconds: 间隔秒数（schedule_type="interval" 时必填，>= 60）
        llm_provider: 可选，指定 cron 任务的 LLM 提供商（默认使用 .env 中 CRON_LLM_PROVIDER）
        llm_model: 可选，指定 cron 任务的 LLM 模型名（默认使用 .env 中 CRON_LLM_MODEL）
    """
    if _engine_ref is None:
        return "错误：调度器尚未初始化"

    job = CronJob(
        name=name.strip(),
        task_prompt=task_prompt.strip(),
        schedule_type=schedule_type,
        cron_expr=cron_expr,
        run_at=run_at,
        interval_seconds=interval_seconds,
        llm_provider=llm_provider or None,
        llm_model=llm_model or None,
    )

    err = _engine_ref.add_job(job)
    if err:
        return f"注册失败: {err}"
    return f"定时任务已注册: {job.name} (id={job.job_id})"


@tool
def list_cron_jobs() -> str:
    """列出所有已注册的定时任务及其状态。"""
    if _engine_ref is None:
        return "错误：调度器尚未初始化"
    jobs = _engine_ref._store.get_jobs()
    if not jobs:
        return "当前没有定时任务"
    lines = ["定时任务列表："]
    for j in jobs:
        status = "启用" if j.enabled else "暂停"
        schedule = j.cron_expr or j.run_at or f"每{j.interval_seconds}秒"
        lines.append(
            f"  [{j.job_id}] {j.name} | {schedule} | {status} "
            f"| LLM: {j.llm_provider or '(默认)'}/{j.llm_model or '(默认)'}"
        )
        if j.last_run_at:
            lines[-1] += f" | 上次: {j.last_run_at}"
    return "\n".join(lines)


@tool
def remove_cron_job(job_id: str) -> str:
    """删除指定 ID 的定时任务。

    Args:
        job_id: 任务 ID（可通过 list_cron_jobs 获取）
    """
    if _engine_ref is None:
        return "错误：调度器尚未初始化"
    ok = _engine_ref.remove_job(job_id)
    if ok:
        return f"定时任务已删除: {job_id}"
    return f"未找到任务: {job_id}"


_CRON_MGMT_TOOLS = [add_cron_job, list_cron_jobs, remove_cron_job]


# ===== 执行区 =====
logger = get_logger("cron_tools")
