"""api 型采集通道：基于 httpx（GitHub API 等）。"""
from __future__ import annotations

import httpx

from ...config import load_settings
from .base import FetchedPage
from .cookies import parse_cookie_header


class ApiCollector:
    """无状态的 httpx 抓取器（客户端按需创建，事件循环安全）。"""

    async def fetch(
        self,
        url: str,
        *,
        headers: dict | None = None,
        cookie: str = "",
        timeout: float | None = None,
    ) -> FetchedPage:
        settings = load_settings()
        timeout = timeout or float(settings.get("http_timeout", 20))
        merged_headers = {
            "User-Agent": settings.get("user_agent", "Mozilla/5.0"),
            "Accept": "application/json, text/plain, */*",
        }
        merged_headers.update(headers or {})
        cookies = parse_cookie_header(cookie)

        try:
            async with httpx.AsyncClient(
                timeout=timeout,
                follow_redirects=True,
                headers=merged_headers,
                cookies=cookies,
            ) as client:
                resp = await client.get(url)
        except httpx.HTTPError as exc:
            return FetchedPage(url=url, error=f"请求异常：{exc}")

        json_data = None
        try:
            json_data = resp.json()
        except ValueError:
            json_data = None

        return FetchedPage(
            url=str(resp.url),
            status=resp.status_code,
            html=resp.text,
            text=resp.text,
            json_data=json_data,
            headers=dict(resp.headers),
        )
