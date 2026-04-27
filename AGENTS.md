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

## Tools

- `@tool` from `langchain_core.tools` — **docstring** becomes the LLM prompt, include `Args:` section
- **Output capped** at 4000 chars in `shell_tool/tool.py` (`MAX_OUTPUT_CHARS`)
- `run_command`: uses `SafetySessionPool` with thread‑safe `acquire()`/`release()` (per‑shell Lock)
- Cron has its own isolated pool in `cron_agent._cron_pool`
- All tool calls serialized per shell type — concurrent LLM tool calls queue on the same bash session
- PAGER env vars set to `cat` in `ShellSession.__init__` — do not add `pkill` prefixes to commands

## Agent

- Built via `create_agent(llm, tools, system_prompt)` from `langchain.agents.factory`
- Invoke: `agent.invoke({"messages": [*history, HumanMessage(content=...)])`
- **Streaming**: `agent.astream({"messages": ...}, stream_mode=["messages", "updates"])`
  - Yields `(mode, data)` tuples
  - `mode="messages"`: `(AIMessageChunk, metadata)` with `langgraph_node` key in metadata (`"model"` / `"tools"`)
  - `mode="updates"`: `{node_name: {"messages": [...]}}` — final state for history update
  - Tool calls appear in `AIMessage.tool_calls` (list of dicts: `name`, `args`, `id`)
- MessageHistory: sliding window of **60 messages**, auto‑trim

## Cron scheduler

- `scheduler/` module: APScheduler `BackgroundScheduler` with three trigger types
- Jobs persisted to JSON (`~/.agent_cron_data.json`, atomic write via tmp+replace)
- Each job runs via its own `build_cron_agent()` call (separate LLM instance)
- `once` jobs auto‑disable (`enabled=False`) after execution
- Three Agent‑facing tools: `add_cron_job`, `list_cron_jobs`, `remove_cron_job`

## Web UI

- FastAPI: endpoints grouped in `webui/server.py` — chat (POST+WS+SSE), cron CRUD, reports, config, logs
- Frontend: Vanilla JS SPA (`webui/static/app.js`), dark theme (`style.css`)
- **Markdown rendering**: `marked.js` + `DOMPurify` — `webui/templates/index.html` loads from CDN
- `<think>` tags rendered as collapsible `<details>`
- **Tool display level**: dropdown in chat header (verbose/normal/compact/hidden), saved to `localStorage`
- Tool blocks embedded in agent card as `.tool-block` (gold left border) — do NOT create separate tool cards
- Streaming: WS at `/ws/chat` receives JSON `{"message": "..."}`, returns events: `token`, `tool_call`, `tool_result`, `done`, `error`
- SSE fallback: `GET /api/chat/stream?message=...`

## Safety

- `safety/cleanup.py` auto‑registers atexit + SIGINT/SIGTERM on import — closes all shell sessions and stops scheduler
- `SafetySessionPool`: LRU eviction (max 3), idle timeout (300s), SIGKILL on timeout
- `webui/agent_manager.py` `AgentManager` singleton — thread‑safe, initialized once

## Dependencies (venv, no lockfile)

Key ones: `langchain~=1.2`, `langgraph~=1.1`, `fastapi~=0.136`, `uvicorn`, `APScheduler~=3.11`, `pexpect~=4.9`, `python-dotenv`
