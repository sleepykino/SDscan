"""风控检测：依据平台 risk_control_hints 判定验证码/封禁。

hints 结构：
``{"url_patterns": [...], "page_keywords": [...]}``
"""
from __future__ import annotations

from .base import FetchedPage

# HTTP 状态码层面的风控信号
RISK_STATUS = {401, 403, 429, 503}


def detect_risk(page: FetchedPage, hints: dict) -> str | None:
    """命中风控返回原因字符串，否则返回 None。"""
    if page.status in RISK_STATUS:
        return f"HTTP {page.status}，疑似被拦截"

    url = (page.url or "").lower()
    for pattern in (hints or {}).get("url_patterns", []):
        pattern = str(pattern).strip()
        if pattern and pattern.lower() in url:
            return f"URL 命中风控特征：{pattern}"

    haystack = f"{page.title}\n{page.text}"
    for keyword in (hints or {}).get("page_keywords", []):
        keyword = str(keyword).strip()
        if keyword and keyword in haystack:
            return f"页面命中风控关键词：{keyword}"

    return None
