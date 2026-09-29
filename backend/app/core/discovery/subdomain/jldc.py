"""jldc.me（Anubis 社区聚合库）被动源。"""
from __future__ import annotations

from typing import AsyncIterator

from ..base import Evidence, ProviderContext, ProviderError, ProviderSkipped, SubResult
from ..merge import normalize_sub_host
from . import common

ENDPOINT = "https://jldc.me/anubis/subdomains/{apex}"


class JldcSub:
    code = "jldc"
    display_name = "jldc(Anubis)"

    def is_configured(self, settings: dict) -> bool:
        return bool(settings.get("t2_sub_enabled", {}).get("jldc", True))

    async def run(self, ctx: ProviderContext, apex: str) -> AsyncIterator:
        try:
            data = await common.get_json(ENDPOINT.format(apex=apex), ctx.settings)
        except ProviderSkipped:
            raise
        except Exception as exc:  # noqa: BLE001
            raise ProviderError(f"jldc 请求失败：{exc}") from exc
        if not isinstance(data, list):
            return
        seen: set[str] = set()
        for raw in data:
            host = normalize_sub_host(str(raw))
            if not host or host in seen or not common.belongs(host, apex):
                continue
            seen.add(host)
            yield SubResult(
                host=host, apex=apex,
                evidence=Evidence(
                    provider="jldc", stage="sub",
                    ref_url=ENDPOINT.format(apex=apex),
                ),
            )
