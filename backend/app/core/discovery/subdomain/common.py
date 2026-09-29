"""被动子域源的共享 HTTP 工具。"""
from __future__ import annotations

import httpx

from ..base import ProviderSkipped
from ..merge import normalize_sub_host

# 免费公共源的限流/拒绝/网关故障属于“源本次不可用”，按 skipped 归类而非任务失败
_SOFT_STATUS = {401, 403, 429, 500, 502, 503, 504}


def _raise_for_status(resp: httpx.Response) -> None:
    if resp.status_code in _SOFT_STATUS:
        raise ProviderSkipped(f"{resp.request.url.host} 返回 HTTP {resp.status_code}（限流/不可达）")
    if resp.status_code == 404:
        return
    resp.raise_for_status()


async def get_text(url: str, settings: dict) -> str:
    timeout = float(settings.get("t2_passive_timeout", 15))
    async with httpx.AsyncClient(
        timeout=timeout,
        headers={"User-Agent": settings.get("user_agent", "")},
        follow_redirects=True,
    ) as client:
        resp = await client.get(url)
        _raise_for_status(resp)
        return "" if resp.status_code == 404 else resp.text


async def get_json(url: str, settings: dict):
    timeout = float(settings.get("t2_passive_timeout", 15))
    async with httpx.AsyncClient(
        timeout=timeout,
        headers={"User-Agent": settings.get("user_agent", "")},
        follow_redirects=True,
    ) as client:
        resp = await client.get(url)
        _raise_for_status(resp)
        return None if resp.status_code == 404 else resp.json()


def belongs(host: str, apex: str) -> bool:
    host = normalize_sub_host(host)
    return bool(host) and (host == apex or host.endswith("." + apex))
