"""FOFA / Hunter / Quake 三引擎共享原语（P5 D2）。

三引擎同时服务阶段 A（按主体查资产）与阶段 B（domain 语法查子域）；
各家返回结构以官网文档为准，此处全部防御式 .get 取值，字段缺失不抛异常。
"""
from __future__ import annotations

import base64
from typing import Any

import httpx

from .base import ProviderError, ProviderSkipped

FOFA_URL = "https://fofa.info/api/v1/search/all"
HUNTER_URL = "https://hunter.qianxin.com/openApi/search"
QUAKE_URL = "https://quake.quake360.net/api/v3/search/quake_service"


def qb64(text: str) -> str:
    return base64.b64encode(text.encode("utf-8")).decode("ascii")


class QuerySyntaxError(ProviderError):
    """查询语法在当前账号等级不可用：调用方按降级链切换。"""


class QuotaError(ProviderSkipped):
    """鉴权失败或额度耗尽。"""


# ---------------------------------------------------------------- FOFA
async def fofa_search(settings: dict, query: str, *, max_pages: int,
                      page_size: int, timeout: float) -> list[dict[str, Any]]:
    email = settings.get("fofa_email", "")
    key = settings.get("fofa_key", "")
    if not email or not key:
        raise QuotaError("未配置 FOFA email/key")
    headers = {"User-Agent": settings.get("user_agent", "")}
    fields_attempts = ["host,domain,icp,title", "host,domain,title"]
    last_err = ""
    async with httpx.AsyncClient(timeout=timeout, headers=headers) as client:
        for fields in fields_attempts:
            assets: list[dict] = []
            try:
                for page in range(1, max_pages + 1):
                    params = {
                        "email": email, "key": key, "qbase64": qb64(query),
                        "fields": fields, "size": page_size, "page": page,
                    }
                    resp = await client.get(FOFA_URL, params=params)
                    if resp.status_code in (401, 403):
                        raise QuotaError(f"FOFA 鉴权失败 HTTP {resp.status_code}")
                    if resp.status_code != 200:
                        raise ProviderError(f"FOFA HTTP {resp.status_code}")
                    data = resp.json()
                    if data.get("error"):
                        msg = str(data.get("errmsg") or "FOFA 查询错误")
                        last_err = msg
                        break  # 字段集/语法问题，换最小字段集重试
                    cols = fields.split(",")
                    for row in data.get("results") or []:
                        cells = row if isinstance(row, list) else []
                        getf = lambda name: (  # noqa: E731
                            cells[cols.index(name)]
                            if name in cols and cols.index(name) < len(cells) else ""
                        )
                        assets.append({
                            "host": getf("host"),
                            "domain": getf("domain"),
                            "icp": getf("icp"),
                            "icp_unit": "",
                            "title": getf("title"),
                            "cert_org": "",
                            "url": "",
                            "raw": row,
                        })
                    if len(data.get("results") or []) < page_size:
                        break
                if assets or not last_err:
                    return assets
            except httpx.HTTPError as exc:
                raise ProviderError(f"FOFA 请求失败：{exc}") from exc
    if any(k in last_err for k in ("语法", "权限", "会员", "不能使用", "Invalid", "invalid")):
        raise QuerySyntaxError(last_err)
    raise ProviderError(last_err or "FOFA 无结果")


# ---------------------------------------------------------------- Hunter
def _hunter_asset(item: dict) -> dict:
    return {
        "host": item.get("domain") or item.get("host") or "",
        "domain": item.get("domain") or "",
        "icp": item.get("icp_number") or item.get("icp") or "",
        "icp_unit": item.get("icp_company") or item.get("company") or "",
        "title": item.get("web_title") or item.get("title") or "",
        "cert_org": item.get("cert") or "",
        "url": item.get("url") or "",
        "raw": item,
    }


async def hunter_search(settings: dict, query: str, *, max_pages: int,
                        page_size: int, timeout: float) -> list[dict[str, Any]]:
    key = settings.get("hunter_key", "")
    if not key:
        raise QuotaError("未配置 Hunter api-key")
    headers = {"User-Agent": settings.get("user_agent", "")}
    assets: list[dict] = []
    async with httpx.AsyncClient(timeout=timeout, headers=headers) as client:
        for page in range(1, max_pages + 1):
            params = {
                "api-key": key, "search": qb64(query), "page": page,
                "page_size": min(page_size, 100), "is_web": 3,
            }
            try:
                resp = await client.get(HUNTER_URL, params=params)
            except httpx.HTTPError as exc:
                raise ProviderError(f"Hunter 请求失败：{exc}") from exc
            if resp.status_code in (401, 403, 429):
                raise QuotaError(f"Hunter 鉴权/限额 HTTP {resp.status_code}")
            if resp.status_code != 200:
                raise ProviderError(f"Hunter HTTP {resp.status_code}")
            data = resp.json()
            code = data.get("code")
            if code not in (200, "200"):
                msg = str(data.get("message") or "Hunter 查询错误")
                if any(k in msg for k in ("积分", "额度", "权限", "key", "Key", "认证")):
                    raise QuotaError(msg)
                if any(k in msg for k in ("语法", "不支持")):
                    raise QuerySyntaxError(msg)
                raise ProviderError(msg)
            arr = ((data.get("data") or {}).get("arr")) or []
            assets.extend(_hunter_asset(item) for item in arr if isinstance(item, dict))
            total = int((data.get("data") or {}).get("total") or 0)
            if page * page_size >= total or len(arr) < page_size:
                break
    return assets


# ---------------------------------------------------------------- Quake
def _deep_find(obj: Any, keys: tuple[str, ...]) -> str:
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k in keys and isinstance(v, str) and v:
                return v
        for v in obj.values():
            found = _deep_find(v, keys)
            if found:
                return found
    elif isinstance(obj, list):
        for v in obj:
            found = _deep_find(v, keys)
            if found:
                return found
    return ""


def _quake_asset(item: dict) -> dict:
    service = item.get("service") or {}
    http = service.get("http") or {}
    title = http.get("title") or _deep_find(service, ("title",))
    cert_org = _deep_find(service, ("organization", "org", "subject_O"))
    host = item.get("domain") or item.get("hostname") or ""
    return {
        "host": host,
        "domain": item.get("domain") or host,
        "icp": _deep_find(item, ("icp_number", "icp")),
        "icp_unit": _deep_find(item, ("icp_company", "company_name")),
        "title": title,
        "cert_org": cert_org,
        "url": f"{service.get('name', 'http')}://{host}:{item.get('port', '')}" if host else "",
        "raw": item,
    }


async def quake_search(settings: dict, query: str, *, max_pages: int,
                       page_size: int, timeout: float) -> list[dict[str, Any]]:
    token = settings.get("quake_key", "")
    if not token:
        raise QuotaError("未配置 Quake X-QuakeToken")
    headers = {
        "X-QuakeToken": token,
        "Content-Type": "application/json",
        "User-Agent": settings.get("user_agent", ""),
    }
    assets: list[dict] = []
    async with httpx.AsyncClient(timeout=timeout, headers=headers) as client:
        for page in range(1, max_pages + 1):
            body = {
                "query": query, "start": (page - 1) * page_size,
                "size": page_size, "latest": True,
            }
            try:
                resp = await client.post(QUAKE_URL, json=body)
            except httpx.HTTPError as exc:
                raise ProviderError(f"Quake 请求失败：{exc}") from exc
            if resp.status_code in (401, 403, 429):
                raise QuotaError(f"Quake 鉴权/限额 HTTP {resp.status_code}")
            if resp.status_code != 200:
                raise ProviderError(f"Quake HTTP {resp.status_code}")
            data = resp.json()
            code = data.get("code")
            if code not in (0, "0"):
                msg = str(data.get("message") or "Quake 查询错误")
                if any(k in msg for k in ("额度", "积分", "权限", "token", "Token", "认证")):
                    raise QuotaError(msg)
                if any(k in msg for k in ("语法", "query")):
                    raise QuerySyntaxError(msg)
                raise ProviderError(msg)
            items = data.get("data") or []
            assets.extend(_quake_asset(i) for i in items if isinstance(i, dict))
            if len(items) < page_size:
                break
    return assets


ENGINE_SEARCH = {
    "fofa": fofa_search,
    "hunter": hunter_search,
    "quake": quake_search,
}

# (查询式, 该查询是否按备案主体精确命中)
def apex_query_plans(engine: str, full_name: str, aliases: list[str]) -> list[tuple[str, bool]]:
    if engine == "fofa":
        plan = [(f'icp.name="{full_name}"', True), (f'cert.subject="{full_name}"', False)]
        plan += [(f'cert="{a}"', False) for a in aliases]
        plan += [(f'title="{a}"', False) for a in aliases]
        return plan
    if engine == "hunter":
        plan = [(f'icp.name="{full_name}"', True), (f'cert="{full_name}"', False)]
        plan += [(f'web.name="{a}"', False) for a in aliases]
        return plan
    # quake
    plan = [(f'icp_company:"{full_name}"', True), (f'cert:"{full_name}"', False)]
    plan += [('service.http.title:"%s"' % a, False) for a in aliases]
    return plan


def subdomain_query(engine: str, apex: str) -> str:
    if engine == "fofa":
        return f'domain="{apex}"'
    if engine == "hunter":
        return f'domain.suffix="{apex}"'
    return f'domain:"{apex}"'
