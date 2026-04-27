# ===== 引入区 =====
import asyncio
import base64
import json
import os
import threading
import time
from typing import Any

from playwright.async_api import async_playwright

from safety.cleanup import register
from logger import get_logger


# ===== 定义区 =====
STATE_DIR = os.path.expanduser("~/.agent_browser_state")
os.makedirs(STATE_DIR, exist_ok=True)


def _url_safe(url: str) -> str | None:
    if not url or not isinstance(url, str):
        return "URL 不能为空"
    url = url.strip()
    if url.startswith("file://") or url.startswith("chrome://") or url.startswith("about:") or url.startswith("data:") or url.startswith("javascript:"):
        return f"不支持的协议: {url.split(':')[0]}://"
    return None


class BrowserSession:
    def __init__(self):
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._playwright = None
        self._browser = None
        self._context = None
        self._page = None
        self._lock = threading.Lock()
        self._ready = False
        self._current_url = ""
        register(self.close)

    def start(self) -> str | None:
        with self._lock:
            if self._ready:
                return None
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
            self._browser = await self._playwright.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-setuid-sandbox"],
            )
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

    # ── sync wrappers ──

    def _sync(self, coro):
        if not self._loop or not self._thread:
            return "[错误] 浏览器未启动"
        future = asyncio.run_coroutine_threadsafe(coro, self._loop)
        try:
            return future.result(timeout=60)
        except asyncio.TimeoutError:
            return "[超时] 浏览器操作超时(60s)"

    def navigate(self, url: str, timeout: int = 30) -> str:
        err = _url_safe(url)
        if err:
            return err
        if not url.startswith("http"):
            url = "https://" + url

        async def _nav():
            resp = await self._page.goto(url, timeout=timeout * 1000, wait_until="domcontentloaded")
            self._current_url = self._page.url
            return resp

        result = self._sync(_nav())
        if result is None:
            return f"页面加载失败: {self._current_url}"
        return f"已导航到 {self._current_url}"

    def click(self, selector: str, timeout: int = 10) -> str:
        def _click():
            return self._page.click(selector, timeout=timeout * 1000)
        result = self._sync(_click())
        if isinstance(result, str) and result.startswith("["):
            return result
        return f"已点击: {selector}"

    def fill(self, selector: str, text: str, timeout: int = 10) -> str:
        def _fill():
            return self._page.fill(selector, text, timeout=timeout * 1000)
        result = self._sync(_fill())
        if isinstance(result, str) and result.startswith("["):
            return result
        return f"已填写 {selector}: {text[:50]}"

    def select(self, selector: str, value: str, timeout: int = 10) -> str:
        def _select():
            return self._page.select_option(selector, value, timeout=timeout * 1000)
        self._sync(_select())
        return f"已选择 {selector}: {value}"

    def extract_text(self, selector: str = "body") -> str:
        def _extract():
            return self._page.inner_text(selector)
        text = self._sync(_extract())
        if isinstance(text, str) and text.startswith("["):
            return text
        return text or "(空)"

    def extract_html(self, selector: str = "body") -> str:
        def _extract():
            return self._page.inner_html(selector)
        html = self._sync(_extract())
        if isinstance(html, str) and html.startswith("["):
            return html
        return html or "(空)"

    def screenshot(self) -> str:
        async def _shot():
            buf = await self._page.screenshot(type="png", full_page=False)
            return "data:image/png;base64," + base64.b64encode(buf).decode()
        return self._sync(_shot())

    def go_back(self) -> str:
        self._sync(self._page.go_back())
        self._current_url = self._sync(self._page.url)
        return f"后退到: {self._current_url}"

    def go_forward(self) -> str:
        self._sync(self._page.go_forward())
        self._current_url = self._sync(self._page.url)
        return f"前进到: {self._current_url}"

    def refresh(self) -> str:
        self._sync(self._page.reload())
        self._current_url = self._sync(self._page.url)
        return f"已刷新: {self._current_url}"

    def scroll(self, direction: str = "down", amount: int = 300) -> str:
        dx, dy = 0, 0
        if direction == "down": dy = amount
        elif direction == "up": dy = -amount
        elif direction == "right": dx = amount
        elif direction == "left": dx = -amount
        self._sync(self._page.evaluate(f"window.scrollBy({dx}, {dy})"))
        return f"已滚动 {direction} {amount}px"

    def execute_js(self, script: str) -> str:
        result = self._sync(self._page.evaluate(script))
        return str(result) if result is not None else "(无返回值)"

    def wait(self, ms: int = 500) -> str:
        self._sync(asyncio.sleep(ms / 1000))
        return f"已等待 {ms}ms"

    def save_state(self, name: str = "default") -> str:
        def _save():
            return self._context.storage_state()
        state = self._sync(_save())
        path = os.path.join(STATE_DIR, f"{name}.json")
        with open(path, "w") as f:
            json.dump(state, f)
        return f"已保存浏览器状态: {name}"

    def load_state(self, name: str = "default") -> str:
        path = os.path.join(STATE_DIR, f"{name}.json")
        if not os.path.exists(path):
            return f"未找到保存的状态: {name}"

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

        err = self._sync(_load())
        return f"已加载浏览器状态: {name}"

    def list_states(self) -> list[str]:
        if not os.path.isdir(STATE_DIR):
            return []
        return [f.replace(".json", "") for f in os.listdir(STATE_DIR) if f.endswith(".json")]

    def get_page_info(self) -> dict:
        url = self._current_url
        title = ""
        if self._loop and self._ready:
            title = self._sync(self._page.title()) if self._page else ""
        return {"url": url, "title": title}

    def get_screenshot_base64(self) -> str | None:
        try:
            return self.screenshot()
        except Exception:
            return None

    def close(self):
        with self._lock:
            self._ready = False
            if self._loop and not self._loop.is_closed():
                loop = self._loop
                async def _clean():
                    if self._page:
                        try:
                            await self._page.close()
                        except Exception:
                            pass
                    if self._context:
                        try:
                            await self._context.close()
                        except Exception:
                            pass
                    if self._browser:
                        try:
                            await self._browser.close()
                        except Exception:
                            pass
                    if self._playwright:
                        try:
                            await self._playwright.stop()
                        except Exception:
                            pass
                try:
                    future = asyncio.run_coroutine_threadsafe(_clean(), loop)
                    future.result(timeout=10)
                except Exception:
                    pass
                loop.call_soon_threadsafe(loop.stop)
            self._playwright = self._browser = self._context = self._page = None
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
