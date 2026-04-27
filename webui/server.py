# ===== 引入区 =====
import json
import logging
import os
import time

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from webui.agent_manager import get_manager

from logger import get_logger


# ===== 定义区 =====

# --- request/response 模型 ---

class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=4000)

class ChatResponse(BaseModel):
    output: str
    error: str | None = None

class CronJobCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    task_prompt: str = Field(..., min_length=1, max_length=2000)
    schedule_type: str = Field(default="cron", pattern=r"^(cron|once|interval)$")
    cron_expr: str | None = None
    run_at: str | None = None
    interval_seconds: int | None = None
    llm_provider: str | None = None
    llm_model: str | None = None


# --- FastAPI 应用 ---

app = FastAPI(
    title="Agent Web UI",
    description="Agent 项目的 Web 管理界面",
    version="1.0.0",
)

STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")
TEMPLATES_DIR = os.path.join(os.path.dirname(__file__), "templates")

if os.path.isdir(STATIC_DIR):
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


# --- 首页 ---

@app.get("/", response_class=HTMLResponse)
async def index():
    index_path = os.path.join(TEMPLATES_DIR, "index.html")
    if not os.path.exists(index_path):
        return HTMLResponse("<h1>UI 模板未找到</h1>", status_code=404)
    with open(index_path, "r", encoding="utf-8") as f:
        return HTMLResponse(f.read())


# --- 初始化 ---

@app.post("/api/init")
async def initialize():
    mgr = get_manager()
    err = mgr.initialize()
    if err:
        raise HTTPException(status_code=500, detail=err)
    return {"status": "ok", "config": mgr.get_config()}


@app.get("/api/status")
async def status():
    mgr = get_manager()
    return {"ready": mgr.ready, "config": mgr.get_config()}


# --- 聊天 ---

@app.post("/api/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    mgr = get_manager()
    if not mgr.ready:
        err = mgr.initialize()
        if err:
            return ChatResponse(output="", error=err)

    result = mgr.chat(req.message)
    return ChatResponse(output=result.get("output", ""), error=result.get("error"))


@app.get("/api/chat/history")
async def chat_history():
    mgr = get_manager()
    return {"messages": mgr.get_history()}


# --- WebSocket 聊天 ---

@app.websocket("/ws/chat")
async def websocket_chat(ws: WebSocket):
    await ws.accept()
    mgr = get_manager()

    if not mgr.ready:
        err = mgr.initialize()
        if err:
            await ws.send_json({"type": "error", "content": err})
            await ws.close()
            return

    try:
        while True:
            data = await ws.receive_text()
            try:
                parsed = json.loads(data)
                msg = parsed.get("message", "")
            except (json.JSONDecodeError, TypeError):
                msg = data

            if not msg.strip():
                continue

            result = mgr.chat(msg)
            if result.get("error"):
                await ws.send_json({"type": "error", "content": result["error"]})
            else:
                await ws.send_json({"type": "response", "content": result["output"]})
    except WebSocketDisconnect:
        pass
    except Exception:
        logger.exception("WebSocket 异常")


# --- Cron 管理 ---

@app.get("/api/cron/jobs")
async def list_cron_jobs():
    mgr = get_manager()
    if not mgr.cron_store:
        raise HTTPException(status_code=503, detail="调度器未初始化")
    jobs = mgr.cron_store.get_jobs()
    return {
        "jobs": [
            {
                "job_id": j.job_id,
                "name": j.name,
                "task_prompt": j.task_prompt,
                "schedule_type": j.schedule_type,
                "cron_expr": j.cron_expr,
                "run_at": j.run_at,
                "interval_seconds": j.interval_seconds,
                "enabled": j.enabled,
                "llm_provider": j.llm_provider,
                "llm_model": j.llm_model,
                "last_run_at": j.last_run_at,
            }
            for j in jobs
        ]
    }


@app.post("/api/cron/jobs")
async def create_cron_job(job: CronJobCreate):
    from scheduler.models import CronJob as CronJobModel

    mgr = get_manager()
    if not mgr.cron_engine:
        raise HTTPException(status_code=503, detail="调度器未初始化")

    new_job = CronJobModel(
        name=job.name,
        task_prompt=job.task_prompt,
        schedule_type=job.schedule_type,
        cron_expr=job.cron_expr,
        run_at=job.run_at,
        interval_seconds=job.interval_seconds,
        llm_provider=job.llm_provider,
        llm_model=job.llm_model,
    )
    err = mgr.cron_engine.add_job(new_job)
    if err:
        raise HTTPException(status_code=400, detail=err)
    return {"status": "ok", "job_id": new_job.job_id}


@app.delete("/api/cron/jobs/{job_id}")
async def delete_cron_job(job_id: str):
    mgr = get_manager()
    if not mgr.cron_engine:
        raise HTTPException(status_code=503, detail="调度器未初始化")
    ok = mgr.cron_engine.remove_job(job_id)
    if not ok:
        raise HTTPException(status_code=404, detail=f"任务不存在: {job_id}")
    return {"status": "ok"}


@app.get("/api/cron/reports")
async def list_cron_reports():
    mgr = get_manager()
    if not mgr.cron_store:
        raise HTTPException(status_code=503, detail="调度器未初始化")
    reports = mgr.cron_store.get_all_reports(limit=30)
    return {
        "reports": [
            {
                "report_id": r.report_id,
                "job_id": r.job_id,
                "triggered_at": r.triggered_at,
                "task_prompt": r.task_prompt,
                "summary": r.summary(120),
                "read": r.read,
            }
            for r in reversed(reports)
        ]
    }


@app.get("/api/cron/reports/{report_id}")
async def get_cron_report(report_id: str):
    mgr = get_manager()
    if not mgr.cron_store:
        raise HTTPException(status_code=503, detail="调度器未初始化")
    report = mgr.cron_store.get_report(report_id)
    if not report:
        raise HTTPException(status_code=404, detail="报告不存在")
    mgr.cron_store.mark_report_read(report_id)
    return {
        "report_id": report.report_id,
        "job_id": report.job_id,
        "triggered_at": report.triggered_at,
        "task_prompt": report.task_prompt,
        "output": report.output,
        "conversation": report.conversation,
        "read": True,
    }


# --- 系统 ---

@app.get("/api/config")
async def get_config():
    mgr = get_manager()
    return mgr.get_config()


@app.get("/api/logs")
async def get_logs(lines: int = 50):
    log_file = "app.log"
    if not os.path.exists(log_file):
        return {"logs": []}
    try:
        with open(log_file, "r", encoding="utf-8") as f:
            all_lines = f.readlines()
        return {"logs": all_lines[-min(lines, 200):]}
    except (OSError, IOError):
        return {"logs": [], "error": "无法读取日志文件"}


@app.on_event("shutdown")
async def shutdown():
    mgr = get_manager()
    mgr.shutdown()
    logger.info("Web UI 服务关闭")


# ===== 执行区 =====
logger = get_logger("webui_server")

if __name__ == "__main__":
    import uvicorn
    host = os.getenv("WEBUI_HOST", "0.0.0.0")
    port = int(os.getenv("WEBUI_PORT", "8080"))
    print(f"启动 Web UI: http://{host}:{port}")
    uvicorn.run(app, host=host, port=port, log_level="info")
