"""FOFA / Hunter / Quake 的阶段 B providers：domain 语法查子域。"""
from __future__ import annotations

from typing import AsyncIterator

from ..base import Evidence, ProviderContext, ProviderSkipped, SubResult
from ..engines import (
    ENGINE_SEARCH,
    QuerySyntaxError,
    QuotaError,
    subdomain_query,
)
from ..merge import normalize_sub_host


class _EngineSub:
    code = ""

    def is_configured(self, settings: dict) -> bool:
        if not settings.get("t2_sub_enabled", {}).get(self.code, True):
            return False
        if self.code == "fofa":
            return bool(settings.get("fofa_email") and settings.get("fofa_key"))
        if self.code == "hunter":
            return bool(settings.get("hunter_key"))
        return bool(settings.get("quake_key"))

    async def run(self, ctx: ProviderContext, apex: str) -> AsyncIterator:
        search = ENGINE_SEARCH[self.code]
        query = subdomain_query(self.code, apex)
        try:
            assets = await search(
                ctx.settings, query,
                max_pages=ctx.max_pages, page_size=ctx.page_size,
                timeout=ctx.http_timeout,
            )
        except QuerySyntaxError as exc:
            raise ProviderSkipped(f"{self.code} domain 语法不可用：{exc}") from exc
        except QuotaError:
            raise
        await ctx.log(f"> [{self.code}] {query} → {len(assets)} 条资产")
        seen: set[str] = set()
        for asset in assets:
            host = normalize_sub_host(str(asset.get("host") or asset.get("domain") or ""))
            if not host or host in seen:
                continue
            if host != apex and not host.endswith("." + apex):
                continue
            seen.add(host)
            yield SubResult(
                host=host, apex=apex,
                evidence=Evidence(
                    provider=self.code, stage="sub",
                    site_name=str(asset.get("title") or ""),
                    ref_url=str(asset.get("url") or host),
                    detail={"query": query},
                ),
            )


class FofaSub(_EngineSub):
    code = "fofa"


class HunterSub(_EngineSub):
    code = "hunter"


class QuakeSub(_EngineSub):
    code = "quake"
