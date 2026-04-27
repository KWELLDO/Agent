# ===== 引入区 =====
import asyncio
import base64
import json
import os
import re
import threading
import time
from typing import Any
from urllib.parse import unquote

from playwright.async_api import async_playwright

from safety.cleanup import register
from logger import get_logger


# ===== 定义区 =====
STATE_DIR = os.path.expanduser("~/.agent_browser_state")
os.makedirs(STATE_DIR, exist_ok=True)

_DANGEROUS_SCHEMES = re.compile(
    r"^(file|chrome|about|data|blob|ftp|javascript|chrome-extension|chrome-devtools|view-source)",
    re.IGNORECASE,
)

_JS_BLOCKLIST_RE = re.compile(
    r"\b(document|cookie|localStorage|sessionStorage|indexedDB|open|fetch|XMLHttpRequest|"
    r"WebSocket|navigator\.sendBeacon|Worker|SharedWorker|ServiceWorker)\b"
)


def _sanitize_state_name(name: str) -> str | None:
    if not name or not isinstance(name, str):
        return None
    name = name.strip()
    if not name:
        return None
    if ".." in name or "/" in name or "\\" in name:
        return None
    if len(name) > 100:
        return None
    return re.sub(r"[^a-zA-Z0-9_\-]", "", name)


def _url_safe(url: str) -> str | None:
    if not url or not isinstance(url, str):
        return "URL 不能为空"
    url = url.strip()
    decoded = unquote(url)

    # check raw and decoded
    for u in (url, decoded):
        if _DANGEROUS_SCHEMES.match(u):
            scheme = u.split(":")[0].lower()
            return f"不支持的协议: {scheme}://"

    return None





class BrowserSession:
    def __init__(self):
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._playwright = None
        self._browser = None
        self._context = None
        self._page = None
        self._op_lock = threading.Lock()
        self._start_lock = threading.Lock()
        self._ready = False
        self._current_url = ""

        self._closed = False
        register(self.close)

    def start(self) -> str | None:
        with self._start_lock:
            if self._ready:
                return None
            self._closed = False
            self._loop = asyncio.new_event_loop()
            self._thread = threading.Thread(target=self._run_loop, daemon=True)
            self._thread.start()
            future = asyncio.run_coroutine_threadsafe(self._async_start(), self._loop)
            try:
                err = future.result(timeout=30)
                if err:
                    return err
                self._ready = True
                logger.info("BrowserSession 启动成功")
                return None
            except Exception as e:
                return f"浏览器启动失败: {e}"

    def _run_loop(self):
        asyncio.set_event_loop(self._loop)
        self._loop.run_forever()

    async def _async_start(self):
        try:
            self._playwright = await async_playwright().start()
            proxy = os.getenv("HTTP_PROXY") or os.getenv("HTTPS_PROXY")
            launch_args = {"headless": True}
            if proxy:
                launch_args["proxy"] = {"server": proxy}
            self._browser = await self._playwright.chromium.launch(**launch_args)
            self._context = await self._browser.new_context(
                viewport={"width": 1280, "height": 720},
                locale="zh-CN",
            )
            self._context.on("dialog", lambda d: d.dismiss())
            self._page = await self._context.new_page()
            await self._page.goto("about:blank")
            self._current_url = "about:blank"
            return None
        except Exception as e:
            logger.exception("浏览器启动异常")
            return str(e)

    def _sync(self, coro, timeout: float = 60):
        if not self._loop or not self._thread or self._closed:
            return "[错误] 浏览器未启动或已关闭"
        future = asyncio.run_coroutine_threadsafe(coro, self._loop)
        try:
            return future.result(timeout=timeout)
        except asyncio.TimeoutError:
            return "[超时] 浏览器操作超时"

    def _op(self, fn, timeout=60):
        with self._op_lock:
            return fn()

    def navigate(self, url: str, timeout: int = 30) -> str:
        target = url
        to = timeout

        def _run():
            nonlocal target, to
            err = _url_safe(target)
            if err:
                return err
            if not target.startswith("http"):
                target = "https://" + target

            async def _nav():
                resp = await self._page.goto(target, timeout=to * 1000, wait_until="domcontentloaded")
                self._current_url = self._page.url
                return resp

            result = self._sync(_nav(), timeout=to + 10)
            if result is None:
                return f"页面加载失败: {self._current_url}"
            return f"已导航到 {self._current_url}"

        return self._op(_run)

    def click(self, selector: str, timeout: int = 10) -> str:
        def _run():
            async def _click():
                await self._page.click(selector, timeout=timeout * 1000)
            self._sync(_click(), timeout=timeout + 10)
            return f"已点击: {selector}"

        return self._op(_run)

    def fill(self, selector: str, text: str, timeout: int = 10) -> str:
        def _run():
            async def _fill():
                await self._page.fill(selector, text, timeout=timeout * 1000)
            self._sync(_fill(), timeout=timeout + 10)
            return f"已填写 {selector}: {text[:50]}"

        return self._op(_run)

    def select(self, selector: str, value: str, timeout: int = 10) -> str:
        def _run():
            async def _select():
                await self._page.select_option(selector, value, timeout=timeout * 1000)
            self._sync(_select(), timeout=timeout + 10)
            return f"已选择 {selector}: {value}"

        return self._op(_run)

    def extract_text(self, selector: str = "body") -> str:
        def _run():
            async def _extract():
                return await self._page.inner_text(selector)
            text = self._sync(_extract())
            return text or "(空)"

        return self._op(_run)

    def extract_html(self, selector: str = "body") -> str:
        def _run():
            async def _extract():
                return await self._page.inner_html(selector)
            html = self._sync(_extract())
            return html or "(空)"

        return self._op(_run)

    def screenshot(self) -> str:
        def _run():
            async def _shot():
                buf = await self._page.screenshot(type="png", full_page=False)
                return "data:image/png;base64," + base64.b64encode(buf).decode()
            return self._sync(_shot())

        return self._op(_run)

    def go_back(self) -> str:
        def _run():
            async def _back():
                await self._page.go_back()
                self._current_url = self._page.url
            self._sync(_back())
            return f"后退到: {self._current_url}"

        return self._op(_run)

    def go_forward(self) -> str:
        def _run():
            async def _forward():
                await self._page.go_forward()
                self._current_url = self._page.url
            self._sync(_forward())
            return f"前进到: {self._current_url}"

        return self._op(_run)

    def refresh(self) -> str:
        def _run():
            async def _refresh():
                await self._page.reload()
                self._current_url = self._page.url
            self._sync(_refresh())
            return f"已刷新: {self._current_url}"

        return self._op(_run)

    def scroll(self, direction: str = "down", amount: int = 300) -> str:
        def _run():
            dx, dy = 0, 0
            if direction == "down":
                dy = amount
            elif direction == "up":
                dy = -amount
            elif direction == "right":
                dx = amount
            elif direction == "left":
                dx = -amount
            async def _scroll():
                await self._page.evaluate(f"window.scrollBy({dx}, {dy})")
            self._sync(_scroll())
            return f"已滚动 {direction} {amount}px"

        return self._op(_run)

    def execute_js(self, script: str) -> str:
        def _run():
            if _JS_BLOCKLIST_RE.search(script):
                return f"[安全拦截] 脚本包含危险操作: {_JS_BLOCKLIST_RE.findall(script)}"

            async def _exec():
                try:
                    result = await self._page.evaluate(
                        f"(() => {{ 'use strict'; try {{ return ({script}); }} catch(e) {{ return '[JS错误] ' + e.message; }} }})()"
                    )
                    return str(result)
                except Exception as e:
                    return f"[执行错误] {e}"

            return self._sync(_exec())

        return self._op(_run)

    def wait(self, ms: int = 500) -> str:
        async def _wait():
            await asyncio.sleep(ms / 1000)
        self._sync(_wait())
        return f"已等待 {ms}ms"

    def save_state(self, name: str = "default") -> str:
        def _run():
            safe = _sanitize_state_name(name)
            if safe is None:
                return f"无效的状态名称: {name}"
            async def _save():
                return await self._context.storage_state()
            state = self._sync(_save())
            path = os.path.join(STATE_DIR, f"{safe}.json")
            with open(path, "w") as f:
                json.dump(state, f)
            return f"已保存浏览器状态: {safe}"

        return self._op(_run)

    def load_state(self, name: str = "default") -> str:
        def _run():
            safe = _sanitize_state_name(name)
            if safe is None:
                return f"无效的状态名称: {name}"
            path = os.path.join(STATE_DIR, f"{safe}.json")
            if not os.path.exists(path):
                return f"未找到保存的状态: {safe}"

            async def _load():
                if self._context:
                    await self._context.close()
                with open(path) as f:
                    state = json.load(f)
                self._context = await self._browser.new_context(
                    storage_state=state,
                    viewport={"width": 1280, "height": 720},
                    locale="zh-CN",
                )
                self._context.on("dialog", lambda d: d.dismiss())
                self._page = await self._context.new_page()
                await self._page.goto("about:blank")
                self._current_url = "about:blank"

            self._sync(_load())
            return f"已加载浏览器状态: {safe}"

        return self._op(_run)

    def list_states(self) -> list[str]:
        if not os.path.isdir(STATE_DIR):
            return []
        return sorted(f.replace(".json", "") for f in os.listdir(STATE_DIR) if f.endswith(".json"))

    def get_page_info(self) -> dict:
        title = ""
        if self._loop and self._ready:
            async def _title():
                return await self._page.title()
            title = self._sync(_title())
        return {"url": self._current_url, "title": title or ""}

    def get_screenshot_base64(self) -> str | None:
        try:
            return self.screenshot()
        except Exception:
            return None

    def close(self):
        with self._op_lock:
            if self._closed:
                return
            self._closed = True
            self._ready = False
            loop = self._loop

            if loop and not loop.is_closed():
                async def _clean():
                    for target in (self._page, self._context, self._browser, self._playwright):
                        if target is None:
                            continue
                        try:
                            if hasattr(target, "close"):
                                await target.close()
                            if hasattr(target, "stop"):
                                await target.stop()
                        except Exception:
                            pass

                try:
                    future = asyncio.run_coroutine_threadsafe(_clean(), loop)
                    future.result(timeout=10)
                except Exception:
                    pass
                finally:
                    loop.call_soon_threadsafe(loop.stop)

            self._playwright = self._browser = self._context = self._page = None
            self._loop = None
            self._thread = None
            logger.info("BrowserSession 已关闭")


_session: BrowserSession | None = None
_session_lock = threading.Lock()


def get_session() -> BrowserSession:
    global _session
    if _session is None:
        with _session_lock:
            if _session is None:
                _session = BrowserSession()
    return _session


# ===== 执行区 =====
logger = get_logger("browser_session")
