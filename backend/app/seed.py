"""种子数据：平台规则、敏感规则、语法字典（幂等写入）。

注意：各平台结果选择器为初版经验值，目标站点改版后需用平台配置页的「测试」
按钮实测校准（详细设计 §7.1 备注）。
"""
from __future__ import annotations

from sqlalchemy import select

from .database import SessionLocal
from .models import Platform, SensitiveRule, SyntaxDict

COMMON_RISK_HINTS = {
    "url_patterns": [
        "wappass.baidu.com",
        "captcha",
        "verify",
        "antispider",
        "safe.so.com",
        "check",
    ],
    "page_keywords": [
        "百度安全验证",
        "安全验证",
        "请输入验证码",
        "人机验证",
        "访问过于频繁",
        "网络不给力",
        "Just a moment",
        "Access Denied",
    ],
}

# code, 名称, 通道, URL 模板, page_start, page_step, 选择器
PLATFORMS: list[dict] = [
    {
        "code": "baidu",
        "name": "百度",
        "channel_type": "web",
        "url_template": "https://www.baidu.com/s?wd={keyword}&pn={page}",
        "page_start": 0,
        "page_step": 10,
        "selectors": {
            "container": "div.result.c-container, div.c-container",
            "title": "h3 a",
            "link": "h3 a::attr(href)",
        },
        "notes": "链接为百度跳转链，T5 跟进正文后会回填最终 URL",
    },
    {
        "code": "bing",
        "name": "必应",
        "channel_type": "web",
        "url_template": "https://cn.bing.com/search?q={keyword}&first={page}",
        "page_start": 1,
        "page_step": 10,
        "selectors": {
            "container": "li.b_algo",
            "title": "h2 a",
            "link": "h2 a::attr(href)",
        },
    },
    {
        "code": "so360",
        "name": "360搜索",
        "channel_type": "web",
        "url_template": "https://www.so.com/s?q={keyword}&pn={page}",
        "page_start": 1,
        "page_step": 10,
        "selectors": {
            "container": "li.res-list, div.res-list",
            "title": "h3 a",
            "link": "h3 a::attr(href)",
        },
    },
    {
        "code": "github",
        "name": "GitHub(API)",
        "channel_type": "api",
        "url_template": (
            "https://api.github.com/search/repositories"
            "?q={keyword}&page={page}&per_page=30"
        ),
        "page_start": 1,
        "page_step": 1,
        "selectors": {
            "items_path": "items",
            "title_path": "full_name",
            "link_path": "html_url",
            "description_path": "description",
        },
        "headers": {"Accept": "application/vnd.github+json"},
        "notes": "token 在「全局设置」中配置后自动注入 Authorization 头",
    },
    {
        "code": "github_web",
        "name": "GitHub(网页备用)",
        "channel_type": "web",
        "url_template": "https://github.com/search?q={keyword}&type=repositories&p={page}",
        "page_start": 1,
        "page_step": 1,
        "selectors": {
            "container": "li.repo-list-item, div[data-testid='results-list'] > div",
            "title": "a.v-align-middle, h3 a",
            "link": "a.v-align-middle::attr(href), h3 a::attr(href)",
        },
        "notes": "API 通道不可用时的备用通道，选择器需实测",
    },
    {
        "code": "gitee",
        "name": "Gitee",
        "channel_type": "web",
        "url_template": "https://search.gitee.com/?skin=rec&type=repository&q={keyword}",
        "page_start": 0,
        "page_step": 0,
        "selectors": {
            "container": "div.item, div.repository-search-item",
            "title": "a.title, a.header",
            "link": "a.title::attr(href), a.header::attr(href)",
        },
    },
    {
        "code": "cnnvd",
        "name": "CNNVD",
        "channel_type": "web",
        "url_template": "https://www.cnnvd.org.cn/home/globalSearch?keyword={keyword}",
        "page_start": 0,
        "page_step": 0,
        "selectors": {
            "container": "div.list_main ul li, ul.list_list li",
            "title": "a",
            "link": "a::attr(href)",
        },
    },
    {
        "code": "freebuf",
        "name": "FreeBuf",
        "channel_type": "web",
        "url_template": "https://www.freebuf.com/search?search={keyword}&activeType=1",
        "page_start": 0,
        "page_step": 0,
        "selectors": {
            "container": "div.search-result-item, div.article-item",
            "title": "a.title, h4 a",
            "link": "a.title::attr(href), h4 a::attr(href)",
        },
        "notes": "前端渲染较重，若解析为 0 条请实测校准选择器",
    },
    {
        "code": "pansoso",
        "name": "盘搜搜",
        "channel_type": "web",
        "url_template": "https://www.pansoso.com/zh/{keyword}",
        "page_start": 0,
        "page_step": 0,
        "selectors": {
            "container": "div.search-list li, ul.list li",
            "title": "a",
            "link": "a::attr(href)",
        },
    },
    {
        "code": "wenku",
        "name": "百度文库",
        "channel_type": "web",
        "url_template": "https://wenku.baidu.com/search?word={keyword}&pn={page}",
        "page_start": 0,
        "page_step": 10,
        "selectors": {
            "container": "div.search-result-item, li.document-item",
            "title": "a.title, a.doc-title",
            "link": "a.title::attr(href), a.doc-title::attr(href)",
        },
    },
    {
        "code": "docin",
        "name": "豆丁网",
        "channel_type": "web",
        "url_template": (
            "https://www.docin.com/search.do?nkey={keyword}"
            "&searchcat=1001&currentPage={page}"
        ),
        "page_start": 1,
        "page_step": 1,
        "selectors": {
            "container": "div.docin-layout-list-item, li.result-item",
            "title": "a.title, h3 a",
            "link": "a.title::attr(href), h3 a::attr(href)",
        },
    },
    {
        "code": "doc88",
        "name": "道客巴巴",
        "channel_type": "web",
        "url_template": "https://www.doc88.com/tag/{keyword}",
        "page_start": 0,
        "page_step": 0,
        "selectors": {
            "container": "div.doc_list li, ul.list li",
            "title": "a",
            "link": "a::attr(href)",
        },
    },
    {
        "code": "yuque",
        "name": "语雀",
        "channel_type": "web",
        "url_template": (
            "https://www.yuque.com/search?q={keyword}&type=content&tab=group"
            "&p={page}&sence=searchPage&scope=%2F"
        ),
        "page_start": 1,
        "page_step": 1,
        "selectors": {
            "container": "a.search-result-item, div.ResultCard",
            "title": "span.title, h3",
            "link": "self::a::attr(href)",
        },
        "notes": "SPA 页面，选择器需实测；container 直接为 a 时 link 用 self 轴",
    },
    {
        "code": "csdn",
        "name": "CSDN",
        "channel_type": "web",
        "url_template": "https://so.csdn.net/so/search?q={keyword}&t=all&p={page}",
        "page_start": 1,
        "page_step": 1,
        "selectors": {
            "container": "div.res-list-item, div.result-item",
            "title": "span.title-link, a.title, h3 a",
            "link": "span.title-link a::attr(href), a.title::attr(href), h3 a::attr(href)",
        },
    },
]

# 名称, 分类, 级别, 正则, 描述
RULES: list[dict] = [
    {
        "name": "内网 IP 地址",
        "category": "内网信息",
        "level": "high",
        "pattern": (
            r"(^|\D)(10\.\d{1,3}\.\d{1,3}\.\d{1,3}"
            r"|192\.168\.\d{1,3}\.\d{1,3}"
            r"|172\.(?:1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3})(\D|$)"
        ),
        "description": "RFC1918 私有网段地址外露",
    },
    {
        "name": "身份证号码",
        "category": "证件号码",
        "level": "high",
        "pattern": r"\b\d{17}[\dXx]\b",
        "description": "18 位居民身份证号",
    },
    {
        "name": "弱口令/账号密码",
        "category": "运维凭据",
        "level": "high",
        "pattern": r"(?:root|admin|administrator)\s*[:：]\s*\S{6,}",
        "description": "root/admin 账号后跟密码串",
    },
    {
        "name": "password 赋值",
        "category": "运维凭据",
        "level": "high",
        "pattern": r"password\s*[:：=]\s*\S{6,}",
        "description": "配置/代码中的密码字段",
    },
    {
        "name": "MySQL 连接串",
        "category": "运维凭据",
        "level": "high",
        "pattern": r"jdbc:mysql://\S+",
        "description": "JDBC MySQL 数据库连接串",
    },
    {
        "name": "手机号",
        "category": "联系方式",
        "level": "medium",
        "pattern": r"(?<!\d)1[3-9]\d{9}(?!\d)",
        "description": "中国大陆手机号",
    },
    {
        "name": "运维关键词",
        "category": "运维凭据",
        "level": "medium",
        "pattern": r"堡垒机|VPN|运维平台|后台管理|备份文件",
        "description": "运维入口/敏感设施关键词",
    },
    {
        "name": "员工隐私关键词",
        "category": "员工隐私",
        "level": "medium",
        "pattern": r"通讯录|身份证复印件|家庭住址|工号",
        "description": "员工隐私相关材料关键词",
    },
    {
        "name": "业务敏感词",
        "category": "业务敏感词",
        "level": "low",
        "pattern": r"会议纪要|内部文件|不予公开|工资表|人事任免",
        "description": "不宜公开的业务材料关键词",
    },
]

# 名称, 模板, 表达式
SYNTAX_DICTS: list[dict] = [
    {
        "name": "T2 官网加权词",
        "template_type": "T2",
        "expression": "{keyword} 官网",
    },
    {
        "name": "T3 附件排查语法",
        "template_type": "T3",
        "expression": (
            "site:{domain} (filetype:pdf OR filetype:doc OR filetype:docx "
            "OR filetype:xls OR filetype:xlsx OR filetype:ppt)"
        ),
    },
    {
        "name": "T4 风险页面核查语法",
        "template_type": "T4",
        "expression": (
            "site:{domain} (inurl:admin OR inurl:login OR inurl:manage "
            "OR inurl:test OR inurl:backup OR intitle:后台 OR intitle:登录)"
        ),
    },
    {
        "name": "T5 内容核查语法",
        "template_type": "T5",
        "expression": "site:{domain}",
    },
]


def seed_all() -> None:
    """幂等播种：已存在的 code/规则名不重复插入，不覆盖用户修改。"""
    db = SessionLocal()
    try:
        existing_codes = {c for (c,) in db.execute(select(Platform.code)).all()}
        for item in PLATFORMS:
            if item["code"] in existing_codes:
                continue
            db.add(
                Platform(
                    code=item["code"],
                    name=item["name"],
                    channel_type=item["channel_type"],
                    url_template=item["url_template"],
                    page_start=item["page_start"],
                    page_step=item["page_step"],
                    selectors=item.get("selectors", {}),
                    headers=item.get("headers", {}),
                    risk_control_hints=dict(COMMON_RISK_HINTS),
                    enabled=True,
                    notes=item.get("notes", ""),
                )
            )

        existing_names = {n for (n,) in db.execute(select(SensitiveRule.name)).all()}
        for item in RULES:
            if item["name"] in existing_names:
                continue
            db.add(SensitiveRule(**item, enabled=True))

        existing_expr = {
            (t, e)
            for t, e in db.execute(
                select(SyntaxDict.template_type, SyntaxDict.expression)
            ).all()
        }
        for item in SYNTAX_DICTS:
            key = (item["template_type"], item["expression"])
            if key in existing_expr:
                continue
            db.add(SyntaxDict(**item, enabled=True))

        db.commit()
    finally:
        db.close()
