"""站长开放平台·企业备案实时查询 provider（付费 API，按主办单位反查域名）。

GET https://openapi.chinaz.net/v1/1001/getdamainplus
    ?companyname={全称}&page={p}&APIKey={key}&ChinazVer=1.0
"""
from __future__ import annotations

from typing import AsyncIterator
from urllib.parse import quote

import httpx

from ..base import ApexResult, Evidence, ProviderContext, ProviderError, ProviderSkipped

ENDPOINT = "https://openapi.chinaz.net/v1/1001/getdamainplus"


class ChinazApex:
    code = "chinaz"
    display_name = "站长备案API"

    def is_configured(self, settings: dict) -> bool:
        return bool(
            settings.get("t2_apex_enabled", {}).get("chinaz", True)
            and settings.get("chinaz_key")
        )

    async def run(self, ctx: ProviderContext) -> AsyncIterator:
        key = ctx.settings.get("chinaz_key", "")
        if not key:
            raise ProviderSkipped("未配置站长 APIKey")
        headers = {"User-Agent": ctx.settings.get("user_agent", "")}
        total_pages = 1
        page = 1
        yielded = 0
        async with httpx.AsyncClient(timeout=ctx.http_timeout, headers=headers) as client:
            while page <= total_pages and page <= 50:
                if ctx.cancelled():
                    break
                params = {
                    "companyname": ctx.unit_name,
                    "page": page,
                    "APIKey": key,
                    "ChinazVer": "1.0",
                }
                try:
                    resp = await client.get(
                        ENDPOINT.rstrip("/") + "?" + "&".join(
                            f"{k}={quote(str(v), safe='')}" for k, v in params.items()
                        )
                    )
                except httpx.HTTPError as exc:
                    raise ProviderError(f"站长 API 请求失败：{exc}") from exc
                if resp.status_code in (401, 403, 436):
                    raise ProviderSkipped(f"站长 API 鉴权/额度失败：HTTP {resp.status_code}")
                if resp.status_code != 200:
                    raise ProviderError(f"站长 API HTTP {resp.status_code}")
                data = resp.json()
                if data.get("StateCode") not in (1, "1"):
                    raise ProviderError(f"站长 API 返回异常：{data.get('Reason')}")
                total_pages = int(data.get("TotalPage") or 1)
                rows = data.get("Result") or []
                for row in rows:
                    domain = (row.get("Domain") or "").strip().lower()
                    if not domain:
                        continue
                    yielded += 1
                    yield ApexResult(
                        domain=domain,
                        evidence=Evidence(
                            provider="chinaz",
                            stage="apex",
                            icp_no=row.get("ServiceLicence", "") or row.get("SiteLicense", ""),
                            icp_unit=row.get("UnitName", "") or ctx.unit_name,
                            site_name="",
                            ref_url=f"{ENDPOINT}?companyname={quote(ctx.unit_name)}&page={page}",
                            detail={
                                "site_license": row.get("SiteLicense", ""),
                                "company_type": row.get("CompanyType", ""),
                                "verify_time": row.get("VerifyTime", ""),
                            },
                        ),
                    )
                page += 1
        await ctx.log(f"> [chinaz] 备案反查 {yielded} 个域名")
