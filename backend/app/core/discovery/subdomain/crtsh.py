"""crt.sh 证书透明日志被动源。"""
from __future__ import annotations

from typing import AsyncIterator

from ..base import Evidence, ProviderContext, ProviderSkipped, SubResult
from ..merge import normalize_sub_host
from . import common


class CrtshSub:
    code = "crtsh"
    display_name = "crt.sh证书日志"

    def is_configured(self, settings: dict) -> bool:
        return bool(settings.get("t2_sub_enabled", {}).get("crtsh", True))

    async def run(self, ctx: ProviderContext, apex: str) -> AsyncIterator:
        url = f"https://crt.sh/?q=%.{apex}&output=json"
        try:
            data = await common.get_json(url, ctx.settings)
        except Exception as exc:  # noqa: BLE001 国内可达性不稳，失败交给 pipeline 记录
            raise ProviderSkipped(f"crt.sh 不可达：{exc}") from exc
        if not isinstance(data, list):
            return
        seen: set[str] = set()
        for item in data:
            if not isinstance(item, dict):
                continue
            for raw in str(item.get("name_value", "")).splitlines():
                host = normalize_sub_host(raw)
                if not host or host in seen or not common.belongs(host, apex):
                    continue
                seen.add(host)
                yield _result(host, apex, item)


def _result(host: str, apex: str, item: dict) -> SubResult:
    return SubResult(
        host=host,
        apex=apex,
        evidence=Evidence(
            provider="crtsh", stage="sub",
            ref_url=f"https://crt.sh/?q=%.{apex}",
            detail={"issuer": (item.get("issuer_name") or "")[:200]},
        ),
    )
