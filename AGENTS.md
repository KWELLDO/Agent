# AGENTS.md

## Startup & commands

- **CLI**: `python main.py`
- **Web UI**: `python webui/server.py` (binds `0.0.0.0:8080`, env `WEBUI_HOST`/`WEBUI_PORT`)
- **Python**: `source venv/bin/activate` (3.14)
- **Log**: `app.log`, format `%(asctime)s [%(levelname)s] %(name)s: %(message)s`
- **No test/lint/typecheck infra exists** — ad-hoc testing via Starlette `TestClient`

## Code layout

Every `.py` file follows three **section headers** — never break them:

```
# ===== 引入区 =====   (imports only)
# ===== 定义区 =====   (classes, functions, @tool, constants, singletons)
# ===== 执行区 =====   (logger = get_logger(...), __all__, load_dotenv(), __main__)
```

Logger creation (`logger = get_logger(...)`) goes at the very bottom of 执行区.

## LLM

- **Provider switch**: env `LLM_PROVIDER=deepseek|ollama` — main toggle
- **Cron LLM** is decoupled: env `CRON_LLM_PROVIDER`/`CRON_LLM_MODEL`
- **New provider**: create file in `model_setup/`, wire into `build_llm()` in `__init__.py`
- `DeepSeekThinkingModel` subclass re-injects `reasoning_content` from previous turns into request payload — required for DeepSeek thinking models (`deepseek-v4-pro`, `deepseek-v4-flash`), otherwise API returns 400
- `deepseek-r1` via Ollama does NOT support tool calling
- **HTTP_PROXY** env read by Playwright at startup for browser proxy; set in `.env` for VPN access

## Tools

- `@tool` from `langchain_core.tools` — **docstring** becomes the LLM prompt, include `Args:` section
- **Output capped** at 4000 chars in `shell_tool/tool.py` (`MAX_OUTPUT_CHARS`)
- **Shell config**: `bash` (PTY via pexpect, persistent cd/env) / `nushell` (subprocess `nu -c`, no persistent state). `powershell` removed.
- `run_command`: uses `pool.acquire(shell)`/`release(shell)` with per-shell Lock — all concurrent LLM tool calls serialize on the same shell type
- PAGER env vars set to `cat` in `ShellSession.__init__` — do not add `pkill` prefixes
- `shutil.which()` pre-check before `pexpect.spawn()` — missing binary returns friendly error string
- **Tool registration**: both `main.py` AND `webui/agent_manager.py` must list `+ _BROWSER_TOOLS`

### Browser tools (16)

Module `browser/` — Playwright Chromium persistent session with asyncio background thread.

| Tool | Key notes |
|------|-----------|
| `browser_navigate` | **Only way to access web** — docstring says "不要用 curl/wget" |
| `browser_click(selector, force=False)` | `force=True` falls back to JS `.click()` when element hidden |
| `browser_fill(selector, text, force=False)` | `force=True` falls back to `element.value = ...` when covered |
| `browser_screenshot()` | Returns `data:image/png;base64,...` — inline in agent card |
| `browser_extract_text(selector)` | Default `body` for full page text |
| `browser_save_state/load_state` | Persists cookies+localStorage to `~/.agent_browser_state/*.json` |
| `browser_execute_js` | Regex-blocklist for `document/cookie/fetch/XHR/WebSocket` |

Browser session uses asyncio event loop in a daemon thread; all sync methods use `asyncio.run_coroutine_threadsafe` + `future.result(timeout=60)`. Methods are serialized via `_op_lock`.

### Cron tools (3)

| Tool | Purpose |
|------|---------|
| `add_cron_job(name, task_prompt, schedule_type, ...)` | `cron` / `once` / `interval` |
| `list_cron_jobs()` | Shows all jobs with status |
| `remove_cron_job(job_id)` | Deletes job |

## Agent

- Built via `create_agent(llm, tools, system_prompt)` from `langchain.agents.factory`
- Invoke: `agent.invoke({"messages": [*history, HumanMessage(content=...)])`
- **Streaming**: `agent.astream({"messages": ...}, stream_mode=["messages", "updates"])`
  - Yields `(mode, data)` tuples
  - `mode="messages"`: `(AIMessageChunk, metadata)` with `langgraph_node` key in metadata (`"model"` / `"tools"`) — node name is `"model"` NOT `"agent"`
  - `mode="updates"`: `{node_name: {"messages": [...]}}` — final state for history update
  - Tool calls appear in `AIMessage.tool_calls` (list of dicts: `name`, `args`, `id`)
- MessageHistory: sliding window of **60 messages**, auto‑trim

## Cron scheduler

- `scheduler/` module: APScheduler `BackgroundScheduler` with three trigger types
- Jobs persisted to JSON (`~/.agent_cron_data.json`, atomic write via tmp+replace)
- Each job runs via its own `build_cron_agent()` call (separate LLM instance with its own shell pool)
- `once` jobs auto‑disable (`enabled=False`) after execution

## Web UI

- FastAPI: endpoints in `webui/server.py` — chat (POST+WS+SSE), cron CRUD, reports, config, logs
- **Browser tab** (`#tab-browser`): URL bar, back/forward/refresh, screenshot viewer (polls every 2s)
- Frontend: Vanilla JS SPA (`webui/static/app.js`), dark theme (`style.css`)
- **Markdown rendering**: `marked.js` + `DOMPurify` — `webui/templates/index.html` loads from CDN
- `<think>` tags rendered as collapsible `<details>`
- **Tool display level**: dropdown in chat header (verbose/normal/compact/hidden), saved to `localStorage`
- Tool blocks embedded in agent card as `.tool-block` (3px gold left border) — do NOT create separate tool cards
- Streaming: WS at `/ws/chat` receives JSON `{"message": "..."}`, returns events: `token`, `tool_call`, `tool_result`, `done`, `error`
- SSE fallback: `GET /api/chat/stream?message=...`

## Safety

- `safety/cleanup.py` auto‑registers atexit + SIGINT/SIGTERM on import — closes all shell sessions, stops scheduler, closes browser
- `SafetySessionPool`: LRU eviction (max 3), idle timeout (300s), SIGKILL on timeout, `acquire`/`release` pattern with per-shell Lock
- `BrowserSession`: `_op_lock` serializes all operations, `close()` registered with `safety.cleanup`, URL scheme blocklist, JS execute blocklist
- `webui/agent_manager.py` `AgentManager` singleton — thread‑safe, initialized once

## Dependencies (venv, no lockfile)

Key ones: `langchain~=1.2`, `langgraph~=1.1`, `fastapi~=0.136`, `uvicorn`, `APScheduler~=3.11`, `pexpect~=4.9`, `python-dotenv`, `playwright~=1.58`
