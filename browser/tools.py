# ===== 引入区 =====
from langchain_core.tools import tool

from browser.session import get_session

from logger import get_logger


# ===== 定义区 =====

def _ensure_browser():
    sess = get_session()
    err = sess.start()
    if err:
        return None, f"浏览器启动失败: {err}"
    return sess, None


@tool
def browser_navigate(url: str, timeout: int = 30) -> str:
    """导航到指定 URL 并等待页面加载。支持 http/https，可省略协议（自动补 https://）。

    Args:
        url: 目标网址（如 example.com 或 https://example.com）
        timeout: 加载超时秒数
    """
    sess, err = _ensure_browser()
    if err:
        return err
    return sess.navigate(url, timeout=timeout)


@tool
def browser_click(selector: str, timeout: int = 10) -> str:
    """点击页面中匹配 CSS 选择器的元素。

    Args:
        selector: CSS 选择器（如 #submit, button.primary, a[href*="login"]）
        timeout: 等待元素出现的秒数
    """
    sess, err = _ensure_browser()
    if err:
        return err
    return sess.click(selector, timeout=timeout)


@tool
def browser_fill(selector: str, text: str, timeout: int = 10) -> str:
    """在输入框中填入文本。会先清空原有内容。

    Args:
        selector: CSS 选择器
        text: 要填入的文本
        timeout: 等待元素出现的秒数
    """
    sess, err = _ensure_browser()
    if err:
        return err
    return sess.fill(selector, text, timeout=timeout)


@tool
def browser_select(selector: str, value: str, timeout: int = 10) -> str:
    """从下拉框中选择选项。

    Args:
        selector: 下拉框的 CSS 选择器
        value: 选项的 value 值
        timeout: 等待元素出现的秒数
    """
    sess, err = _ensure_browser()
    if err:
        return err
    return sess.select(selector, value, timeout=timeout)


@tool
def browser_extract_text(selector: str = "body") -> str:
    """提取页面中匹配 CSS 选择器的纯文本内容。默认提取整个页面可见文本。

    Args:
        selector: CSS 选择器，默认 body 提取全文
    """
    sess, err = _ensure_browser()
    if err:
        return err
    return sess.extract_text(selector)


@tool
def browser_extract_html(selector: str = "body") -> str:
    """提取页面中匹配 CSS 选择器的 HTML 内容。默认提取整个页面 body。

    Args:
        selector: CSS 选择器，默认 body
    """
    sess, err = _ensure_browser()
    if err:
        return err
    return sess.extract_html(selector)


@tool
def browser_screenshot() -> str:
    """截取当前页面截图，返回 base64 编码的 data URI 图片，可直接嵌入 HTML。"""
    sess, err = _ensure_browser()
    if err:
        return err
    return sess.screenshot()


@tool
def browser_go_back() -> str:
    """后退到上一个页面。"""
    sess, err = _ensure_browser()
    if err:
        return err
    return sess.go_back()


@tool
def browser_go_forward() -> str:
    """前进到下一个页面。"""
    sess, err = _ensure_browser()
    if err:
        return err
    return sess.go_forward()


@tool
def browser_refresh() -> str:
    """刷新当前页面。"""
    sess, err = _ensure_browser()
    if err:
        return err
    return sess.refresh()


@tool
def browser_scroll(direction: str = "down", amount: int = 300) -> str:
    """滚动页面。

    Args:
        direction: 滚动方向，可选 down / up / left / right
        amount: 滚动像素数
    """
    sess, err = _ensure_browser()
    if err:
        return err
    return sess.scroll(direction, amount)


@tool
def browser_execute_js(script: str) -> str:
    """在页面中执行 JavaScript 代码并返回结果。

    Args:
        script: JavaScript 代码字符串
    """
    sess, err = _ensure_browser()
    if err:
        return err
    return sess.execute_js(script)


@tool
def browser_wait(ms: int = 500) -> str:
    """等待指定的毫秒数，用于等待页面加载或动画完成。

    Args:
        ms: 等待毫秒数
    """
    sess, err = _ensure_browser()
    if err:
        return err
    return sess.wait(ms)


@tool
def browser_save_state(name: str = "default") -> str:
    """保存当前浏览器状态（cookies + localStorage + sessionStorage）到命名 profile。

    Args:
        name: profile 名称，可用 browser_list_states 查看已保存的
    """
    sess, err = _ensure_browser()
    if err:
        return err
    return sess.save_state(name)


@tool
def browser_load_state(name: str = "default") -> str:
    """加载已保存的浏览器状态（恢复登录态）。

    Args:
        name: profile 名称
    """
    sess, err = _ensure_browser()
    if err:
        return err
    return sess.load_state(name)


@tool
def browser_list_states() -> str:
    """列出所有已保存的浏览器状态 profile 名称。"""
    sess, err = _ensure_browser()
    if err:
        return err
    states = sess.list_states()
    if not states:
        return "没有已保存的状态"
    return "已保存的状态:\n" + "\n".join(f"  - {s}" for s in states)


_BROWSER_TOOLS = [
    browser_navigate, browser_click, browser_fill, browser_select,
    browser_extract_text, browser_extract_html,
    browser_screenshot,
    browser_go_back, browser_go_forward, browser_refresh,
    browser_scroll, browser_execute_js, browser_wait,
    browser_save_state, browser_load_state, browser_list_states,
]


# ===== 执行区 =====
logger = get_logger("browser_tools")
