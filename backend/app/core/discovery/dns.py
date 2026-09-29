"""DNS 验活与泛解析识别（仅 DNS 查询，不触碰目标 Web 服务）。

使用标准库 socket + asyncio.to_thread，不引入第三方依赖（P5 约束）。
"""
from __future__ import annotations

import asyncio
import ipaddress
import socket

from .merge import gen_wildcard_prefix


async def resolve_host(host: str, timeout: float = 5.0) -> list[str]:
    """返回去重后的 IPv4 地址列表；解析失败返回空列表。"""
    def _resolve() -> list[str]:
        seen: list[str] = []
        try:
            infos = socket.getaddrinfo(host, None, socket.AF_INET)
        except OSError:
            return []
        for info in infos:
            ip = info[4][0]
            if ip not in seen:
                try:
                    ipaddress.ip_address(ip)
                except ValueError:
                    continue
                seen.append(ip)
        return seen

    try:
        return await asyncio.wait_for(asyncio.to_thread(_resolve), timeout=timeout)
    except Exception:  # noqa: BLE001 解析失败/超时一律视为无记录
        return []


async def detect_wildcard(apex: str, timeout: float = 5.0) -> set[str]:
    """泛解析基线：解析 3 个随机不存在前缀，返回其 IP 集合。

    空集合表示无泛解析；非空时，爆破结果 IP 完全落入该集合的应判为假阳性。
    """
    baseline: set[str] = set()
    for _ in range(3):
        host = f"{gen_wildcard_prefix()}.{apex}"
        baseline.update(await resolve_host(host, timeout))
    return baseline


async def verify_many(hosts: list[str], *, timeout: float = 5.0,
                      concurrency: int = 20) -> dict[str, list[str]]:
    """并发验活，返回 {host: [ip...]}，无解析记录的值为空列表。"""
    sem = asyncio.Semaphore(concurrency)
    result: dict[str, list[str]] = {}

    async def _one(host: str) -> None:
        async with sem:
            result[host] = await resolve_host(host, timeout)

    await asyncio.gather(*(_one(h) for h in hosts))
    return result
