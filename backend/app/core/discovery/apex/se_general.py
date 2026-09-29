"""通用搜索引擎兜底 provider：复用现有平台表与双通道采集（D1/D8）。

查询词由 syntax_dict 启用的 T2 表达式包装（种子「{keyword} 官网」）。
单平台风控/失败只跳过该平台，不做 T1 的 blocked 等待过码。
"""
from __future__ import annotations

from typing import AsyncIterator

from sqlalchemy import select

from ....database import SessionLocal
from ....models import Platform, SyntaxDict
from ...engine.api_collector import ApiCollector
from ...engine.risk import detect_risk
from ...engine.web_collector import web_collector
from ..base import ApexResult, Evidence, ProviderContext
from ..merge import normalize_domain
from ...rule_engine import (
    build_url,
    extract_items,
    page_offset,
    registrable_domain,
    split_lines,
    wrap_keyword,
)


# 内容平台泛域：几乎不可能是目标单位官网（目标本体为这些平台时由 ICP/测绘源覆盖）
_SOCIAL_GENERIC = {"zhihu.com", "weibo.com", "bilibili.com"}


def _self_hosts(platform: Platform) -> set[str]:
    """只过滤「当前正在采集的搜索引擎」自身域名。

    不能过滤全部平台域名——百度/必应等本身也可能是被核查单位（如目标就是百度公司），
    此时它在别的引擎结果里出现的官网不应被误杀；跨引擎串扰靠置信度与人工闸门甄别。
    """
    host = registrable_domain(platform.url_template)
    return ({host} if host else set()) | _SOCIAL_GENERIC


class SeGeneralApex:
    code = "se_general"
    display_name = "通用搜索引擎"

    def __init__(self) -> None:
        self._api = ApiCollector()

    def is_configured(self, settings: dict) -> bool:
        if not settings.get("t2_apex_enabled", {}).get("se_general", True):
            return False
        db = SessionLocal()
        try:
            return bool(
                db.execute(
                    select(Platform.id).where(Platform.enabled.is_(True)).limit(1)
                ).first()
            )
        finally:
            db.close()

    async def run(self, ctx: ProviderContext) -> AsyncIterator:
        db = SessionLocal()
        seen: set[str] = set()
        try:
            stmt = select(Platform).where(Platform.enabled.is_(True)).order_by(Platform.id)
            if ctx.se_platform_ids:
                stmt = stmt.where(Platform.id.in_(ctx.se_platform_ids))
            platforms = list(db.execute(stmt).scalars())
            expression_row = db.execute(
                select(SyntaxDict).where(
                    SyntaxDict.template_type == "T2",
                    SyntaxDict.enabled.is_(True),
                ).order_by(SyntaxDict.id)
            ).scalars().first()
            expression = expression_row.expression if expression_row else ""
            bases = split_lines(ctx.task.keywords) or [ctx.unit_name]
            bases += [ctx.unit_name] if ctx.unit_name not in bases else []
            max_pages = max(ctx.se_max_pages, 1)
            settings = ctx.settings

            for platform in platforms:
                if ctx.cancelled():
                    break
                platform_hit = 0
                stop_platform = False
                for base in bases:
                    if stop_platform:
                        break
                    keyword = wrap_keyword(expression, keyword=base)
                    for logical_page in range(1, max_pages + 1):
                        page_value = page_offset(platform, logical_page)
                        if page_value is None:
                            break  # 该平台不支持继续翻页
                        url = build_url(platform.url_template, keyword, page_value)
                        page_obj = await self._fetch(platform, url, settings)
                        if page_obj.error:
                            await ctx.log(
                                f"> [se_general/{platform.name}] 失败跳过：{page_obj.error[:60]}"
                            )
                            stop_platform = True
                            break
                        if detect_risk(page_obj, platform.risk_control_hints or {}):
                            await ctx.log(
                                f"> [se_general/{platform.name}] 触发风控，跳过该平台"
                            )
                            stop_platform = True
                            break
                        for item in extract_items(page_obj, platform):
                            domain = normalize_domain(item.get("url", ""))
                            if not domain or domain in _self_hosts(platform) or domain in seen:
                                continue
                            seen.add(domain)
                            platform_hit += 1
                            yield ApexResult(
                                domain=domain,
                                evidence=Evidence(
                                    provider="se_general",
                                    stage="apex",
                                    site_name=item.get("title", "")[:255],
                                    ref_url=item.get("url", "")[:2000],
                                    detail={
                                        "platform": platform.name,
                                        "keyword": keyword,
                                    },
                                ),
                            )
                if platform_hit:
                    await ctx.log(
                        f"> [se_general/{platform.name}] 归集 {platform_hit} 个域名"
                    )
        finally:
            db.close()

    async def _fetch(self, platform: Platform, url: str, settings: dict):
        if platform.channel_type == "api":
            headers = dict(platform.headers or {})
            token = settings.get("github_token", "")
            if token and platform.code.startswith("github"):
                headers.setdefault("Authorization", f"Bearer {token}")
            return await self._api.fetch(
                url,
                headers=headers,
                cookie=platform.cookie or "",
                timeout=float(settings.get("http_timeout", 20)),
            )
        return await web_collector.fetch(
            url,
            cookie=platform.cookie or "",
            extra_headers=dict(platform.headers or {}),
            timeout=float(settings.get("http_timeout", 20)),
        )
