"""RapidDNS 被动源（HTML 表格解析）。"""
from __future__ import annotations

from typing import AsyncIterator

from parsel import Selector

from ..base import Evidence, ProviderContext, ProviderError, ProviderSkipped, SubResult
from ..merge import normalize_sub_host
from . import common

ENDPOINT = "https://rapiddns.io/subdomain/{apex}?full=1#result"


class RapidDnsSub:
    code = "rapiddns"
    display_name = "RapidDNS"

    def is_configured(self, settings: dict) -> bool:
        return bool(settings.get("t2_sub_enabled", {}).get("rapiddns", True))

    async def run(self, ctx: ProviderContext, apex: str) -> AsyncIterator:
        try:
            html = await common.get_text(ENDPOINT.format(apex=apex), ctx.settings)
        except ProviderSkipped:
            raise
        except Exception as exc:  # noqa: BLE001
            raise ProviderError(f"RapidDNS 请求失败：{exc}") from exc
        if not html:
            return
        sel = Selector(text=html)
        seen: set[str] = set()
        for td in sel.css("table#table tbody tr td:first-child"):
            host = normalize_sub_host(td.xpath("string(.)").get() or "")
            if not host or host in seen or not common.belongs(host, apex):
                continue
            seen.add(host)
            yield SubResult(
                host=host, apex=apex,
                evidence=Evidence(
                    provider="rapiddns", stage="sub",
                    ref_url=ENDPOINT.format(apex=apex),
                ),
            )
