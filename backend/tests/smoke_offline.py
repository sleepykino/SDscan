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


def test_pansoso_selectors() -> None:
    """盘搜搜（2026-09-20 实测配置）：_{page} 后缀分页 + div.pss 结构。"""
    from app.seed import PLATFORMS

    conf = {p["code"]: p for p in PLATFORMS}["pansoso"]

    class P:
        channel_type = "web"
        selectors = conf["selectors"]
        page_start = conf["page_start"]
        page_step = conf["page_step"]

    assert page_offset(P(), 1) == 1
    assert page_offset(P(), 2) == 2  # 旧配置 page_step=0 时此处为 None
    url = build_url(conf["url_template"], "测试", 2)
    assert url == "https://www.pansoso.com/zh/%E6%B5%8B%E8%AF%95_2"

    html = (
        "<html><body>"
        '<div class="pss"><h2><a href="https://www.pansoso.com/qw/1/" target="_blank">'
        "文件 测试.pdf</a></h2><div class=\"des\">描述</div></div>"
        '<div class="pss"><h2><a href="/qw/2/">第二个</a></h2></div>'
        "</body></html>"
    )
    items = extract_items(FetchedPage(url="https://www.pansoso.com/zh/x_1", html=html), P())
    assert len(items) == 2, items
    assert items[0]["title"] == "文件 测试.pdf"
    assert items[0]["url"] == "https://www.pansoso.com/qw/1/"
    assert items[1]["url"] == "https://www.pansoso.com/qw/2/"


def test_doc88_selectors() -> None:
    """道客巴巴（2026-09-20 实测配置）：/search/post.do AJAX 接口 + sd-list 结构。"""
    from app.seed import PLATFORMS

    conf = {p["code"]: p for p in PLATFORMS}["doc88"]

    class P:
        channel_type = "web"
        selectors = conf["selectors"]
        page_start = conf["page_start"]
        page_step = conf["page_step"]

    assert page_offset(P(), 3) == 3
    url = build_url(conf["url_template"], "测试", 2)
    assert url == (
        "https://www.doc88.com/search/post.do?from=1&h=1&p=2"
        "&q=%E6%B5%8B%E8%AF%95&pageRange=0&pageNum=0&ct=0"
    )

    html = (
        "<html><body>"
        '<div class="sd-list-box"><div class="sd-list-con">'
        '<h3 class="sd-type-title"><a href="https://www.doc88.com/p-111.html" '
        'class="sd-title" title="测试报告">测试<span>报告</span></a></h3>'
        '<div class="sd-list-detail"><a class="sd-cover" '
        'href="https://www.doc88.com/p-111.html?format=PPT"></a></div>'
        "</div></div></body></html>"
    )
    items = extract_items(FetchedPage(url="https://www.doc88.com/x", html=html), P())
    assert len(items) == 1, items
    assert items[0]["title"] == "测试 报告"
    assert items[0]["url"] == "https://www.doc88.com/p-111.html"


def test_docin_url_and_headers() -> None:
    """豆丁网（2026-09-20 实测配置）：必须带 Referer，currentPage 翻页。"""
    from app.seed import PLATFORMS

    conf = {p["code"]: p for p in PLATFORMS}["docin"]
    assert conf["headers"] == {"Referer": "https://www.docin.com/"}
    url = build_url(conf["url_template"], "测试", 2)
    assert url == (
        "https://www.docin.com/search.do?nkey=%E6%B5%8B%E8%AF%95"
        "&searchcat=1001&searchType_banner=p&currentPage=2"
    )
    # 选择器可在样例结构上运行（真实结构待限流解除后校准）
    html = (
        "<html><body><div class=\"result-list\">"
        '<div class="doc-list-style2"><dl><dt><a href="/p-97067608.html" '
        'title="普通话教学总结">普通话教学总结</a></dt></dl></div>'
        "</div></body></html>"
    )

    class P:
        channel_type = "web"
        selectors = conf["selectors"]
        page_start = conf["page_start"]
        page_step = conf["page_step"]

    items = extract_items(FetchedPage(url="https://www.docin.com/x", html=html), P())
    assert items and items[0]["url"] == "https://www.docin.com/p-97067608.html", items


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


# ================================================================ P5 T2
def test_engine_query_plans() -> None:
    import base64
    from app.core.discovery.engines import (
        apex_query_plans,
        qb64,
        subdomain_query,
    )

    assert qb64("a") == base64.b64encode(b"a").decode()
    fofa_plan = apex_query_plans("fofa", "示例有限公司", ["示例"])
    assert fofa_plan[0] == ('icp.name="示例有限公司"', True)
    assert any('cert="示例"' in q for q, _ in fofa_plan)
    assert subdomain_query("fofa", "x.com") == 'domain="x.com"'
    assert subdomain_query("hunter", "x.com") == 'domain.suffix="x.com"'
    quake_plan = apex_query_plans("quake", "示例有限公司", [])
    assert quake_plan[0][0].startswith('icp_company:"')
    # 降级链：精确备案查询排在别名模糊查询之前
    assert fofa_plan[0][1] is True and fofa_plan[-1][1] is False


def test_merge_confidence_and_evidence() -> None:
    from app.core.discovery import merge as mg
    from app.core.discovery.base import Evidence

    init_db()
    db = SessionLocal()
    try:
        task = models.Task(name="P5-smoke", template_type="T2",
                           unit_name="示例科技有限公司", keywords="示例云\n示例",
                           platform_ids=[], max_pages=1, stats={})
        db.add(task)
        db.flush()

        # high：ICP 主办单位全称精确一致
        row, ev, is_new = mg.upsert_apex(
            db, task, "https://www.shili.com/",
            Evidence(provider="miit", icp_no="京ICP备1号",
                     icp_unit="示例科技有限公司", site_name="示例官网"),
            ["示例云"],
        )
        assert is_new and row.domain == "shili.com"
        assert row.confidence == "high" and row.provider == "miit"
        assert ev is not None

        # 同 provider/ref_url 证据幂等
        again, ev2, _ = mg.upsert_apex(
            db, task, "shili.com",
            Evidence(provider="miit", icp_no="京ICP备1号",
                     icp_unit="示例科技有限公司", ref_url=""),
            ["示例云"],
        )
        assert again.id == row.id and ev2 is None

        # 第二源仅标题命中别名且交叉 → medium（2 源 + site_name 命中别名）
        _, ev3, _ = mg.upsert_apex(
            db, task, "shili.com",
            Evidence(provider="fofa", site_name="示例云平台",
                     ref_url="https://host/1"),
            ["示例云"],
        )
        db.refresh(row)
        assert ev3 is not None and row.confidence == "high"  # 已 high 不降级

        # low：新域名只有通用搜索单源标题
        low_row, _, _ = mg.upsert_apex(
            db, task, "http://news.other.com/x",
            Evidence(provider="se_general", site_name="无关页面",
                     ref_url="http://news.other.com/x"),
            ["示例云"],
        )
        assert low_row.domain == "other.com" and low_row.confidence == "low"

        # medium：证书主体命中别名的单源新域名
        med_row, _, _ = mg.upsert_apex(
            db, task, "cert.example.cn",
            Evidence(provider="hunter", cert_org="示例云计算分公司",
                     ref_url="https://cert.example.cn"),
            ["示例云"],
        )
        assert med_row.confidence == "medium"

        # 子域归并与越界保护
        sub_row, sub_ev, sub_new = mg.upsert_sub(
            db, task, "WWW.shili.com", "shili.com",
            Evidence(provider="crtsh", stage="sub", ref_url="crt")
        )
        assert sub_new and sub_row.domain == "www.shili.com"
        assert sub_row.parent_domain == "shili.com" and sub_row.layer == "sub"
        db.commit()
    finally:
        db.close()


def _test_subdomain_guard():
    """不属于 apex 的 host 必须抛错。"""
    from app.core.discovery import merge as mg
    from app.core.discovery.base import Evidence

    db = SessionLocal()
    try:
        task = db.execute(select(models.Task).where(
            models.Task.name == "P5-smoke")).scalar_one()
        try:
            mg.upsert_sub(db, task, "www.evil.com", "shili.com",
                          Evidence(provider="crtsh", stage="sub"))
            raise AssertionError("越界子域未被拦截")
        except ValueError:
            pass
        # 清理冒烟数据（含证据/域名/任务）
        tid = task.id
        db.execute(models.DomainEvidence.__table__.delete().where(
            models.DomainEvidence.task_id == tid))
        db.execute(models.DomainList.__table__.delete().where(
            models.DomainList.task_id == tid))
        db.delete(task)
        db.commit()
    finally:
        db.close()


def test_dns_wildcard_and_verify(monkey_hosts=None) -> None:
    """泛解析基线 + 验活聚合（注入假解析，不产生真实网络）。"""
    import asyncio
    from app.core.discovery import dns

    fake = {
        "sdscan-xxx.shili.com": ["1.1.1.1"],
        "sdscan-yyy.shili.com": ["1.1.1.1"],
        "sdscan-zzz.shili.com": ["1.1.1.1"],
        "www.shili.com": ["2.2.2.2"],
        "vpn.shili.com": ["1.1.1.1"],   # 落入泛解析基线
        "oa.shili.com": [],
    }

    async def fake_resolve(host: str, timeout: float = 5.0):
        if host.startswith("sdscan-"):
            return ["1.1.1.1"]  # 模拟泛解析：随机前缀均解析到同一 IP
        return list(fake.get(host, []))

    orig = dns.resolve_host
    dns.resolve_host = fake_resolve
    try:
        baseline = asyncio.run(dns.detect_wildcard("shili.com"))
        assert baseline == {"1.1.1.1"}, baseline
        out = asyncio.run(dns.verify_many(["www.shili.com", "vpn.shili.com", "oa.shili.com"]))
        assert out["www.shili.com"] == ["2.2.2.2"]
        assert out["vpn.shili.com"] == ["1.1.1.1"]   # 验活只看解析结果
        assert out["oa.shili.com"] == []
    finally:
        dns.resolve_host = orig


def test_migration_idempotent_temp_db() -> None:
    """老库（无 P5 列）迁移两次：补列、回填、幂等。"""
    import tempfile
    from pathlib import Path
    from sqlalchemy import create_engine, inspect, text
    from app import migrations

    tmp = Path(tempfile.mkdtemp()) / "t.db"
    eng = create_engine(f"sqlite:///{tmp.as_posix()}", future=True)
    with eng.begin() as conn:
        conn.execute(text(
            "CREATE TABLE domain_list (id INTEGER PRIMARY KEY, task_id INTEGER, "
            "unit_name TEXT, domain TEXT, source TEXT, status TEXT, created_at TIMESTAMP)"
        ))
        conn.execute(text(
            "INSERT INTO domain_list (id, task_id, unit_name, domain, source, status, created_at) "
            "VALUES (1, 1, '旧单位', 'old.com', 'baidu｜x', 'candidate', '2026-01-01 00:00:00')"
        ))

    # 绑定迁移函数到临时引擎执行
    orig_engine = migrations.engine
    migrations.engine = eng
    try:
        migrations.migrate()
        migrations.migrate()
    finally:
        migrations.engine = orig_engine

    cols = {c["name"] for c in inspect(eng).get_columns("domain_list")}
    assert {"layer", "parent_domain", "provider", "confidence",
            "resolved_ip", "alive", "updated_at"} <= cols
    with eng.begin() as conn:
        row = conn.execute(text(
            "SELECT layer, provider, confidence FROM domain_list WHERE id=1"
        )).one()
        assert row == ("apex", "se_general", "low"), row


def test_registry_selection() -> None:
    from app.core.discovery.registry import all_codes, selected_codes

    settings = {"t2_apex_enabled": {"miit": True, "fofa": False},
                "t2_sub_enabled": {"brute": True}}
    assert "miit" in all_codes("apex") and "brute" in all_codes("sub")
    # 空选择 = 设置启用的全部
    apex = selected_codes("apex", {}, settings)
    assert "miit" in apex and "fofa" not in apex
    # 任务显式勾选优先于全局开关
    apex2 = selected_codes("apex", {"apex_providers": ["fofa"]}, settings)
    assert apex2 == ["fofa"]
    sub = selected_codes("sub", {}, settings)
    assert "brute" in sub  # 全局开启时包含爆破（任务内仍需二次授权）


def main() -> None:
    test_url_and_domain()
    test_extract_html()
    test_extract_json()
    test_pansoso_selectors()
    test_doc88_selectors()
    test_docin_url_and_headers()
    test_sensitive()
    test_app_imports()
    test_engine_query_plans()
    test_merge_confidence_and_evidence()
    _test_subdomain_guard()
    test_dns_wildcard_and_verify()
    test_migration_idempotent_temp_db()
    test_registry_selection()
    print("offline smoke ok")


if __name__ == "__main__":
    main()
