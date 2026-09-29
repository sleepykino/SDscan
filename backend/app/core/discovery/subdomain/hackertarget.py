"""HackerTarget hostsearch 被动源（免费限频）。"""
from __future__ import annotations

from typing import AsyncIterator

from ..base import Evidence, ProviderContext, ProviderError, ProviderSkipped, SubResult
from ..merge import normalize_sub_host
from . import common

ENDPOINT = "https://api.hackertarget.com/hostsearch/?q={apex}"


class HackerTargetSub:
    code = "hackertarget"
    display_name = "HackerTarget"

    def is_configured(self, settings: dict) -> bool:
        return bool(settings.get("t2_sub_enabled", {}).get("hackertarget", True))

    async def run(self, ctx: ProviderContext, apex: str) -> AsyncIterator:
        try:
            text = await common.get_text(ENDPOINT.format(apex=apex), ctx.settings)
        except ProviderSkipped:
            raise
        except Exception as exc:  # noqa: BLE001
            raise ProviderError(f"HackerTarget 请求失败：{exc}") from exc
        text = (text or "").strip()
        if not text:
            return
        if text.startswith(("error", "API count exceeded", "error getting")):
            raise ProviderSkipped(f"HackerTarget 限频/无数据：{text[:80]}")
        seen: set[str] = set()
        for line in text.splitlines():
            parts = line.split(",")
            host = normalize_sub_host(parts[0])
            ip = parts[1] if len(parts) > 1 else ""
            if not host or host in seen or not common.belongs(host, apex):
                continue
            seen.add(host)
            yield SubResult(
                host=host, apex=apex,
                evidence=Evidence(
                    provider="hackertarget", stage="sub",
                    ref_url=ENDPOINT.format(apex=apex), detail={"address": ip},
                ),
            )
