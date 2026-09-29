"""主动 DNS 字典爆破 provider（默认关闭，显式授权后才启用）。

- 开关：设置 t2_sub_enabled.brute（默认 False）且任务参数 brute_enabled=True；
- 爆破前做泛解析识别，结果 IP 完全落入泛解析基线的判为假阳性丢弃；
- 仅 DNS 查询，标准库实现，无新增依赖。
"""
from __future__ import annotations

import asyncio
from pathlib import Path
from typing import AsyncIterator

from ....config import WORDLIST_DIR
from ..base import Evidence, ProviderContext, ProviderSkipped, SubResult
from ..dns import detect_wildcard, resolve_host
from ..merge import normalize_sub_host

_BUILTIN_WORDLIST = Path(__file__).resolve().parents[1] / "wordlists" / "subnames.txt"


class BruteDns:
    code = "brute"
    display_name = "DNS字典爆破"

    def is_configured(self, settings: dict) -> bool:
        if not settings.get("t2_sub_enabled", {}).get("brute", False):
            return False
        return bool((self._wordlist_path(settings)).is_file())

    @staticmethod
    def _wordlist_path(settings: dict) -> Path:
        custom = (settings.get("t2_brute_dict_path") or "").strip()
        if custom and Path(custom).is_file():
            return Path(custom)
        user_file = WORDLIST_DIR / "subnames.txt"
        return user_file if user_file.is_file() else _BUILTIN_WORDLIST

    async def run(self, ctx: ProviderContext, apex: str) -> AsyncIterator:
        if not (ctx.task.params or {}).get("brute_enabled"):
            raise ProviderSkipped("任务未开启 DNS 爆破授权")
        settings = ctx.settings
        wordlist = self._wordlist_path(settings)
        if not wordlist.is_file():
            raise ProviderSkipped(f"字典不存在：{wordlist}")

        await ctx.emit({"type": "log",
                        "message": f"! [brute] 已授权对 {apex} 进行主动 DNS 字典爆破（仅 DNS 查询）",
                        "cls": "log-warn"})

        timeout = float(settings.get("t2_dns_timeout", 5))
        concurrency = int(settings.get("t2_brute_concurrency", 50))
        baseline = await detect_wildcard(apex, timeout)
        if baseline:
            await ctx.log(f"> [brute] 检测到泛解析，基线 IP {len(baseline)} 个，将过滤假阳性")

        prefixes = [
            line.strip() for line in wordlist.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.startswith("#")
        ]
        sem = asyncio.Semaphore(concurrency)
        found: list[tuple[str, list[str]]] = []

        async def probe(prefix: str) -> None:
            if ctx.cancelled():
                return
            host = normalize_sub_host(f"{prefix}.{apex}")
            async with sem:
                ips = await resolve_host(host, timeout)
            if not ips:
                return
            if baseline and set(ips).issubset(baseline):
                return  # 泛解析假阳性
            found.append((host, ips))

        # 分批执行，批间留 0.5s 节流；每批 200 个
        batch = 200
        for i in range(0, len(prefixes), batch):
            if ctx.cancelled():
                break
            await asyncio.gather(*(probe(p) for p in prefixes[i:i + batch]))
            await asyncio.sleep(0.5)

        await ctx.log(f"> [brute] 爆破命中 {len(found)} 个子域")
        for host, ips in found:
            yield SubResult(
                host=host, apex=apex,
                evidence=Evidence(
                    provider="brute", stage="sub",
                    detail={"address": ",".join(ips[:4]), "wordlist": wordlist.name},
                ),
            )
