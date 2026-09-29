"""外挂 subfinder provider（Go 单 exe，纯被动多源）。

exe 由使用者自行放入 data/tools/ 并在设置中配置路径；未配置则 skipped。
调用：subfinder -d apex -silent -all
"""
from __future__ import annotations

import asyncio
import os
from typing import AsyncIterator

from ....config import TOOL_DIR
from ..base import Evidence, ProviderContext, ProviderError, ProviderSkipped, SubResult
from ..merge import normalize_sub_host


class SubfinderCli:
    code = "subfinder"
    display_name = "subfinder"

    def is_configured(self, settings: dict) -> bool:
        if not settings.get("t2_sub_enabled", {}).get("subfinder", True):
            return False
        return bool(self._bin_path(settings))

    @staticmethod
    def _bin_path(settings: dict) -> str:
        configured = (settings.get("subfinder_bin_path") or "").strip()
        if configured and os.path.isfile(configured):
            return configured
        # 约定 data/tools/subfinder[.exe]
        for name in ("subfinder.exe", "subfinder"):
            candidate = TOOL_DIR / name
            if candidate.is_file():
                return str(candidate)
        return configured  # 配了但文件不存在：保留配置值，运行时报 skipped

    async def version(self, settings: dict) -> str:
        bin_path = self._bin_path(settings)
        if not bin_path or not os.path.isfile(bin_path):
            raise ProviderSkipped("未找到 subfinder 可执行文件")
        proc = await asyncio.create_subprocess_exec(
            bin_path, "-version",
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT,
        )
        out, _ = await asyncio.wait_for(proc.communicate(), timeout=15)
        return out.decode("utf-8", errors="ignore").strip()

    async def run(self, ctx: ProviderContext, apex: str) -> AsyncIterator:
        settings = ctx.settings
        bin_path = self._bin_path(settings)
        if not bin_path or not os.path.isfile(bin_path):
            raise ProviderSkipped("未找到 subfinder 可执行文件（请放入 data/tools/ 并配置路径）")
        timeout = float(settings.get("t2_passive_timeout", 15)) * 3
        try:
            proc = await asyncio.create_subprocess_exec(
                bin_path, "-d", apex, "-silent", "-all",
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        except asyncio.TimeoutError as exc:
            try:
                proc.kill()
            except Exception:
                pass
            raise ProviderError("subfinder 执行超时") from exc
        except OSError as exc:
            raise ProviderError(f"subfinder 启动失败：{exc}") from exc
        if proc.returncode not in (0, None):
            raise ProviderError(f"subfinder 退出码 {proc.returncode}")

        seen: set[str] = set()
        for raw in stdout.decode("utf-8", errors="ignore").splitlines():
            host = normalize_sub_host(raw)
            if not host or host in seen:
                continue
            if host != apex and not host.endswith("." + apex):
                continue
            seen.add(host)
            yield SubResult(
                host=host, apex=apex,
                evidence=Evidence(provider="subfinder", stage="sub"),
            )
