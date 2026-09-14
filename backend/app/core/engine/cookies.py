"""Cookie 在「Netscape 头字符串」与 httpx/Playwright 结构之间转换。"""
from __future__ import annotations

from urllib.parse import urlparse


def parse_cookie_header(raw: str) -> dict[str, str]:
    """``k1=v1; k2=v2`` -> dict。空值与异常片段忽略。"""
    jar: dict[str, str] = {}
    for part in (raw or "").split(";"):
        part = part.strip()
        if not part or "=" not in part:
            continue
        key, value = part.split("=", 1)
        key = key.strip()
        if key:
            jar[key] = value.strip()
    return jar


def to_cookie_header(cookies: list[dict]) -> str:
    """Playwright cookie 列表 -> 可回填平台配置的头字符串。"""
    return "; ".join(
        f"{c.get('name', '')}={c.get('value', '')}"
        for c in (cookies or [])
        if c.get("name")
    )


def playwright_cookies(raw: str, url: str) -> list[dict]:
    """头字符串 -> Playwright add_cookies 结构（按目标 URL 推导 domain）。"""
    host = urlparse(url).hostname or ""
    domain = "." + host.lstrip(".") if host else ""
    result = []
    for name, value in parse_cookie_header(raw).items():
        result.append(
            {
                "name": name,
                "value": value,
                "domain": domain,
                "path": "/",
            }
        )
    return result
