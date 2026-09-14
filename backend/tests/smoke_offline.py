"""离线冒烟测试：不依赖外网与浏览器内核。

运行（在 backend/ 目录）：
    python tests/smoke_offline.py
"""
from __future__ import annotations

from sqlalchemy import select

from app.core.engine.base import FetchedPage
from app.core.rule_engine import (
    build_url,
    extract_items,
    html_to_text,
    is_in_scope,
    page_offset,
    registrable_domain,
    wrap_keyword,
)
from app.core.sensitive import SensitiveMatcher
from app.database import SessionLocal, init_db
from app import models


class WebPlat:
    channel_type = "web"
    selectors = {
        "container": "div.r",
        "title": "h3 a",
        "link": "h3 a::attr(href)",
    }
    page_start = 0
    page_step = 10


class ApiPlat:
    channel_type = "api"
    selectors = {
        "items_path": "items",
        "title_path": "full_name",
        "link_path": "html_url",
        "description_path": "description",
    }
    page_start = 1
    page_step = 1


def test_url_and_domain() -> None:
    assert build_url("https://x/s?wd={keyword}&pn={page}", "a b", 10) == (
        "https://x/s?wd=a%20b&pn=10"
    )
    assert page_offset(WebPlat(), 1) == 0
    assert page_offset(WebPlat(), 2) == 10
    assert wrap_keyword("site:{domain} (filetype:pdf)", domain="a.com") == (
        "site:a.com (filetype:pdf)"
    )
    assert registrable_domain("https://www.foo.com.cn/a") == "foo.com.cn"
    assert registrable_domain("https://a.b.example.com") == "example.com"
    assert is_in_scope("https://a.b.example.com/x", ["example.com"])
    assert not is_in_scope("https://evil-example.com", ["example.com"])


def test_extract_html() -> None:
    html = (
        "<html><body>"
        '<div class="r"><h3><a href="/p1">标题 一</a></h3></div>'
        '<div class="r"><h3><a href="https://b.com/p2">Title2</a></h3></div>'
        '<div class="r"><h3><a href="javascript:void(0)">js</a></h3></div>'
        "</body></html>"
    )
    page = FetchedPage(url="https://x.com/s", html=html)
    items = extract_items(page, WebPlat())
    assert len(items) == 2, items
    assert items[0]["url"] == "https://x.com/p1"
    assert items[0]["title"] == "标题 一"
    assert items[1]["url"] == "https://b.com/p2"
    assert html_to_text("<html><body><p>正文</p></body></html>") == "正文"


def test_extract_json() -> None:
    page = FetchedPage(
        url="u",
        json_data={
            "items": [
                {"full_name": "o/r", "html_url": "https://gh/r", "description": "d"}
            ]
        },
    )
    items = extract_items(page, ApiPlat())
    assert items[0]["title"] == "o/r"
    assert items[0]["url"] == "https://gh/r"


def test_sensitive() -> None:
    init_db()
    db = SessionLocal()
    try:
        rules = list(db.execute(select(models.SensitiveRule)).scalars())
        matcher = SensitiveMatcher(rules)
        text = "电话 13800138000；内网 192.168.1.1；身份证 11010119900307123X"
        hits = matcher.find(text)
        cats = {r.category for r, _ in hits}
        assert {"联系方式", "内网信息", "证件号码"} <= cats, cats
        for rule, raw in hits:
            masked = SensitiveMatcher.desensitize(rule, raw)
            assert "*" in masked or len(masked) < len(raw), (rule.name, raw, masked)
            assert "192.168.1.1" != masked
    finally:
        db.close()


def test_app_imports() -> None:
    from app.main import app  # noqa: F401  全路由装配校验


def main() -> None:
    test_url_and_domain()
    test_extract_html()
    test_extract_json()
    test_sensitive()
    test_app_imports()
    print("offline smoke ok")


if __name__ == "__main__":
    main()
