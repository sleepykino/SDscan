"""web 型采集通道：Playwright Chromium。

职责：动态渲染页面抓取、每个结果页一张截图、反检测参数注入、
以及半自动人工过码（弹出有头浏览器，完成后回填 Cookie）。

约束（详细设计 §11）：Playwright 并发固定为 1，全局 ``asyncio.Lock`` 保证
单浏览器顺序访问；playwright 采用懒加载导入，未安装浏览器内核时
其余后端功能不受影响，仅 web 通道返回明确错误。
"""
from __future__ import annotations

import asyncio
import uuid

from ...config import SCREENSHOT_DIR, load_settings
from .base import FetchedPage
from .cookies import playwright_cookies, to_cookie_header

_STEALTH_JS = """
Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
Object.defineProperty(navigator, 'languages', {get: () => ['zh-CN', 'zh', 'en']});
Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]});
window.chrome = {runtime: {}};
"""

LAUNCH_ARGS = [
    "--disable-blink-features=AutomationControlled",
    "--no-sandbox",
    "--disable-dev-shm-usage",
]


class WebCollector:
    def __init__(self) -> None:
        self._lock = asyncio.Lock()  # Playwright 并发固定为 1
        self._pw = None
        self._browser = None  # 无头采集浏览器
        self._headed_browser = None  # 有头过码浏览器（按需启动）
        self._solve_ctx = None
        self._solve_page = None
        self._solve_event: asyncio.Event | None = None
        # 进行中的抓取页面登记：取消任务时强制关闭以立即中断抓取
        self._active_pages: set = set()
        # 平台最近一次触发风控的 URL，供有头过码直接打开
        self.last_blocked_url: dict[int, str] = {}

    # ------------------------------------------------------------------ #
    # 浏览器生命周期
    # ------------------------------------------------------------------ #
    async def _ensure_browser(self):
        if self._browser is not None and self._browser.is_connected():
            return self._browser
        from playwright.async_api import async_playwright

        self._pw = await async_playwright().start()
        self._browser = await self._pw.chromium.launch(
            headless=True,
            args=LAUNCH_ARGS,
        )
        return self._browser

    async def aclose(self) -> None:
        for browser, pw in (
            (self._browser, self._pw),
            (self._headed_browser, None),
        ):
            try:
                if browser is not None:
                    await browser.close()
            except Exception:
                pass
        if self._pw is not None:
            try:
                await self._pw.stop()
            except Exception:
                pass
        self._browser = None
        self._headed_browser = None
        self._pw = None

    # ------------------------------------------------------------------ #
    # 常规抓取
    # ------------------------------------------------------------------ #
    async def fetch(
        self,
        url: str,
        *,
        cookie: str = "",
        extra_headers: dict | None = None,
        timeout: float | None = None,
        save_screenshot: bool = True,
    ) -> FetchedPage:
        settings = load_settings()
        timeout_ms = int((timeout or float(settings.get("http_timeout", 20))) * 1000)
        wait_ms = int(settings.get("page_wait_ms", 800))
        screenshot_rel = ""
        if save_screenshot:
            SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
            screenshot_rel = f"screenshots/{uuid.uuid4().hex}.png"

        async with self._lock:
            try:
                browser = await self._ensure_browser()
            except Exception as exc:  # 内核未安装等环境问题
                return FetchedPage(
                    url=url,
                    error=(
                        f"Playwright 不可用（请先执行 python -m playwright install "
                        f"chromium）：{exc}"
                    ),
                )

            context = await browser.new_context(
                user_agent=settings.get("user_agent"),
                locale="zh-CN",
                extra_http_headers=extra_headers or {},
                viewport={"width": 1366, "height": 900},
            )
            await context.add_init_script(_STEALTH_JS)
            if cookie:
                await context.add_cookies(playwright_cookies(cookie, url))
            page = await context.new_page()
            self._active_pages.add(page)
            status = 0
            try:
                response = await page.goto(url, timeout=timeout_ms, wait_until="domcontentloaded")
                if response is not None:
                    status = response.status
                await page.wait_for_timeout(wait_ms)
                html = await page.content()
                title = await page.title()
                try:
                    text = await page.evaluate(
                        "() => document.body ? document.body.innerText : ''"
                    )
                except Exception:
                    text = ""
                if save_screenshot:
                    await page.screenshot(
                        path=str(SCREENSHOT_DIR.parent / screenshot_rel),
                        full_page=False,
                    )
                cookies = await context.cookies()
                return FetchedPage(
                    url=page.url,
                    status=status,
                    html=html,
                    text=text or "",
                    title=title,
                    screenshot_path=screenshot_rel,
                    cookies=cookies,
                )
            except Exception as exc:
                return FetchedPage(url=url, status=status, error=f"页面抓取失败：{exc}")
            finally:
                self._active_pages.discard(page)
                await context.close()

    def close_pages_nowait(self) -> None:
        """取消任务时中断所有进行中的抓取：关闭页面使 goto/截图立刻失败。

        采用同步排程避免在持有采集锁的 fetch 协程内死锁等待。
        """
        pages = list(self._active_pages)
        for page in pages:
            try:
                asyncio.get_running_loop().create_task(self._close_quietly(page))
            except RuntimeError:
                pass

    @staticmethod
    async def _close_quietly(page) -> None:
        try:
            await page.close()
        except Exception:
            pass

    # ------------------------------------------------------------------ #
    # 半自动人工过码
    # ------------------------------------------------------------------ #
    async def start_solve(self, url: str, *, extra_headers: dict | None = None) -> None:
        """弹出有头浏览器到风控页面，等待用户人工完成验证。"""
        from urllib.parse import urlparse

        from playwright.async_api import async_playwright

        if self._headed_browser is not None:
            raise RuntimeError("已有一个过码窗口打开，请先完成或取消")

        settings = load_settings()
        headers = dict(extra_headers or {})
        pw = await async_playwright().start()
        try:
            browser = await pw.chromium.launch(headless=False, args=LAUNCH_ARGS)
            # 携带平台请求头（如豆丁必须的 Referer），否则风控页 URL 会被 204 中止
            context = await browser.new_context(
                user_agent=settings.get("user_agent"),
                locale="zh-CN",
                extra_http_headers=headers,
            )
            await context.add_init_script(_STEALTH_JS)
            page = await context.new_page()
            try:
                await page.goto(
                    url,
                    timeout=60000,
                    wait_until="domcontentloaded",
                    referer=headers.get("Referer") or headers.get("referer"),
                )
            except Exception:
                # 风控 URL 打不开时退回站点首页，保证窗口内仍可人工完成验证
                parsed = urlparse(url)
                home = f"{parsed.scheme}://{parsed.netloc}/" if parsed.netloc else url
                await page.goto(home, timeout=60000, wait_until="domcontentloaded")
        except Exception:
            try:
                await pw.stop()
            except Exception:
                pass
            raise
        self._headed_pw = pw
        self._headed_browser = browser
        self._solve_ctx = context
        self._solve_page = page
        self._solve_event = asyncio.Event()

    async def wait_solve(self) -> None:
        if self._solve_event is not None:
            await self._solve_event.wait()

    async def finish_solve(self) -> str:
        """用户确认过码完成：导出 Cookie 头字符串并关闭有头窗口。"""
        if self._solve_ctx is None:
            raise RuntimeError("没有打开的过码窗口")
        cookies = await self._solve_ctx.cookies()
        raw = to_cookie_header(cookies)
        await self._close_solve()
        return raw

    async def cancel_solve(self) -> None:
        await self._close_solve()

    async def _close_solve(self) -> None:
        for obj in (self._solve_ctx, self._headed_browser):
            try:
                if obj is not None:
                    await obj.close()
            except Exception:
                pass
        if getattr(self, "_headed_pw", None) is not None:
            try:
                await self._headed_pw.stop()
            except Exception:
                pass
        self._headed_pw = None
        self._solve_ctx = None
        self._solve_page = None
        self._headed_browser = None
        if self._solve_event is not None:
            self._solve_event.set()
            self._solve_event = None


# 进程级单例
web_collector = WebCollector()
