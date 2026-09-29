"""AlienVault OTX 被动 DNS 源（免费、无 Key）。"""
from __future__ import annotations

from typing import AsyncIterator

from ..base import Evidence, ProviderContext, ProviderError, ProviderSkipped, SubResult
from ..merge import normalize_sub_host
from . import common

ENDPOINT = "https://otx.alienvault.com/api/v1/indicators/domain/{apex}/passive_dns"


class OtxSub:
    code = "otx"
    display_name = "AlienVault OTX"

    def is_configured(self, settings: dict) -> bool:
        return bool(settings.get("t2_sub_enabled", {}).get("otx", True))

    async def run(self, ctx: ProviderContext, apex: str) -> AsyncIterator:
        try:
            data = await common.get_json(ENDPOINT.format(apex=apex), ctx.settings)
        except ProviderSkipped:
            raise
        except Exception as exc:  # noqa: BLE001
            raise ProviderError(f"OTX 请求失败：{exc}") from exc
        if not isinstance(data, dict):
            return
        seen: set[str] = set()
        for row in data.get("passive_dns") or []:
            host = normalize_sub_host(str(row.get("hostname", "")))
            if not host or host in seen or not common.belongs(host, apex):
                continue
            seen.add(host)
            yield SubResult(
                host=host, apex=apex,
                evidence=Evidence(
                    provider="otx", stage="sub",
                    ref_url=ENDPOINT.format(apex=apex),
                    detail={"address": str(row.get("address", ""))},
                ),
            )
