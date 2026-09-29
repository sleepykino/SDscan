"""FOFA / Hunter / Quake 的阶段 A providers：按单位主体检索资产 → 聚合主域。"""
from __future__ import annotations

from typing import AsyncIterator

from ..base import ApexResult, Evidence, ProviderContext
from ..engines import (
    ENGINE_SEARCH,
    QuerySyntaxError,
    QuotaError,
    apex_query_plans,
)
from ..merge import normalize_domain


class _EngineApex:
    code = ""
    display_name = ""

    def is_configured(self, settings: dict) -> bool:
        if not settings.get("t2_apex_enabled", {}).get(self.code, True):
            return False
        if self.code == "fofa":
            return bool(settings.get("fofa_email") and settings.get("fofa_key"))
        if self.code == "hunter":
            return bool(settings.get("hunter_key"))
        return bool(settings.get("quake_key"))

    async def run(self, ctx: ProviderContext) -> AsyncIterator:
        search = ENGINE_SEARCH[self.code]
        plan = apex_query_plans(self.code, ctx.unit_name, ctx.aliases)
        seen: set[str] = set()
        count = 0
        for query, icp_asserted in plan:
            if ctx.cancelled():
                break
            try:
                assets = await search(
                    ctx.settings, query,
                    max_pages=ctx.max_pages, page_size=ctx.page_size,
                    timeout=ctx.http_timeout,
                )
            except QuerySyntaxError as exc:
                await ctx.log(f"> [{self.code}] 语法降级：{query} 不可用（{exc}）")
                continue
            except QuotaError:
                raise
            await ctx.log(f"> [{self.code}] {query} → {len(assets)} 条资产")
            for asset in assets:
                domain = normalize_domain(asset.get("domain") or asset.get("host") or "")
                if not domain or domain in seen:
                    continue
                seen.add(domain)
                count += 1
                yield ApexResult(
                    domain=domain,
                    evidence=Evidence(
                        provider=self.code,
                        stage="apex",
                        icp_no=str(asset.get("icp") or ""),
                        # 查询式本身按备案主体精确命中时，以单位全称作为归属主体
                        icp_unit=(ctx.unit_name if icp_asserted else str(asset.get("icp_unit") or "")),
                        site_name=str(asset.get("title") or ""),
                        cert_org=str(asset.get("cert_org") or ""),
                        ref_url=str(asset.get("url") or asset.get("host") or query),
                        detail={"query": query},
                    ),
                )
        if count == 0 and not seen:
            await ctx.log(f"> [{self.code}] 无主域产出")


class FofaApex(_EngineApex):
    code = "fofa"
    display_name = "FOFA"


class HunterApex(_EngineApex):
    code = "hunter"
    display_name = "Hunter鹰图"


class QuakeApex(_EngineApex):
    code = "quake"
    display_name = "Quake360"
