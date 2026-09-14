"""URL 拼装、语法包装、结果选择器提取（parsel）与域名工具。"""
from __future__ import annotations

import re
from urllib.parse import quote, unquote, urljoin, urlparse

from parsel import Selector

from ..models import Platform
from .engine.base import FetchedPage

# 常见公开后缀，用于从主机名粗略还原注册域名（T2 域名归集）
_MULTI_LABEL_SUFFIXES = {
    "com.cn",
    "net.cn",
    "org.cn",
    "gov.cn",
    "edu.cn",
    "ac.cn",
    "co.jp",
    "co.kr",
    "com.hk",
}


def page_offset(platform: Platform, logical_page: int) -> int | None:
    """逻辑页码（1 起）换算为 URL 参数值；不支持翻页时仅第 1 页有效。"""
    if logical_page < 1:
        return None
    if platform.page_step == 0:
        return platform.page_start if logical_page == 1 else None
    return platform.page_start + (logical_page - 1) * platform.page_step


def build_url(template: str, keyword: str, page_value: int) -> str:
    """填充 URL 模板，关键词强制百分号编码。"""
    return template.format(keyword=quote(keyword, safe=""), page=page_value)


def wrap_keyword(expression: str | None, domain: str = "", keyword: str = "") -> str:
    """按语法字典表达式包装关键词；表达式为空则原样返回。"""
    if not expression:
        return keyword
    try:
        return expression.format(domain=domain, keyword=keyword)
    except (IndexError, KeyError):
        return keyword


def extract_items(page: FetchedPage, platform: Platform) -> list[dict]:
    """从抓取结果中提取 ``[{title, url}]``，兼容 web(CSS/XPath) 与 api(JSON)。"""
    if platform.channel_type == "api":
        return _extract_json(page.json_data, platform.selectors or {})
    return _extract_html(page.html, page.url, platform.selectors or {})


def _extract_json(data: object, selectors: dict) -> list[dict]:
    if not isinstance(data, dict):
        return []

    def walk(obj, path: str):
        cur = obj
        for part in path.split("."):
            if isinstance(cur, dict) and part in cur:
                cur = cur[part]
            else:
                return None
        return cur

    raw_items = walk(data, selectors.get("items_path", "items"))
    if not isinstance(raw_items, list):
        return []
    items = []
    for node in raw_items:
        if not isinstance(node, dict):
            continue
        title = walk(node, selectors.get("title_path", "title")) or ""
        url = walk(node, selectors.get("link_path", "html_url")) or ""
        desc = walk(node, selectors.get("description_path", "description")) or ""
        if url:
            items.append({"title": str(title), "url": str(url), "snippet": str(desc)})
    return items


def _is_xpath(expr: str) -> bool:
    return expr.startswith("//") or expr.startswith("./") or expr.startswith("(")


def _node_text(node: Selector) -> str:
    return " ".join(t.strip() for t in node.xpath(".//text()").getall() if t.strip())


def _select_value(node: Selector, expr: str, base_url: str) -> tuple[str, str]:
    """返回 (文本, 链接)；调用方按需取用。"""
    if not expr:
        return _node_text(node), ""

    if expr in ("@href", "::attr(href)", "self"):
        href = node.attrib.get("href", "")
        return _node_text(node), urljoin(base_url, href)

    if _is_xpath(expr):
        selected = node.xpath(expr)
    else:
        selected = node.css(expr)

    if "::attr(" in expr:
        value = selected.get(default="").strip()
        return value, urljoin(base_url, value) if value else ""
    if "::text" in expr:
        text = " ".join(t.strip() for t in selected.getall() if t.strip())
        return text, ""
    if expr.startswith("@"):
        value = selected.get(default="").strip()
        return value, urljoin(base_url, value) if value else ""

    first = selected.xpath(".").get()  # 仅判断是否取到元素节点
    element = selected
    if first is not None:
        text_parts = []
        for el in element:
            text_parts.append(_node_text(el))
            href = el.attrib.get("href", "")
            if href:
                return " ".join(text_parts).strip(), urljoin(base_url, href)
        return " ".join(text_parts).strip(), ""
    return "", ""


def _extract_html(html: str, base_url: str, selectors: dict) -> list[dict]:
    if not html:
        return []
    sel = Selector(text=html, base_url=base_url)
    container_expr = selectors.get("container", "")
    title_expr = selectors.get("title", "")
    link_expr = selectors.get("link", "")

    containers = sel.xpath(container_expr) if _is_xpath(container_expr) else sel.css(
        container_expr
    )
    items: list[dict] = []
    seen: set[str] = set()
    for node in containers:
        title, _ = _select_value(node, title_expr, base_url) if title_expr else (
            _node_text(node),
            "",
        )
        if link_expr:
            _, link = _select_value(node, link_expr, base_url)
        else:
            link = node.attrib.get("href", "")
            link = urljoin(base_url, link) if link else ""
        title = (title or "").strip()
        link = (link or "").strip()
        if not link or link in seen:
            continue
        if link.startswith(("javascript:", "mailto:")):
            continue
        seen.add(link)
        items.append({"title": title or link, "url": link})
    return items


def html_to_text(html: str) -> str:
    """去脚本/样式后的正文纯文本（T5 敏感匹配输入）。"""
    if not html:
        return ""
    sel = Selector(text=html)
    sel.remove_namespaces()
    for bad in sel.css("script, style, noscript"):
        bad.drop()
    text = " ".join(t.strip() for t in sel.xpath("//text()").getall() if t.strip())
    return re.sub(r"\s+", " ", text)


def split_lines(value: str) -> list[str]:
    """多行文本按行切分并去空。"""
    return [line.strip() for line in (value or "").splitlines() if line.strip()]


def registrable_domain(url_or_host: str) -> str:
    """从 URL/主机名粗略提取注册域名（用于 T2 归集与 scope 比对）。

    IP 地址返回空串；``www.`` 前缀在结果中去除。
    """
    raw = url_or_host.strip()
    if "://" in raw:
        host = urlparse(raw).hostname or ""
    elif "/" in raw:
        host = urlparse("http://" + raw).hostname or ""
    else:
        host = raw
    host = host.lower().strip(".")
    if not host:
        return ""
    if all(part.isdigit() for part in host.split(".")):
        return ""
    labels = host.split(".")
    if len(labels) <= 2:
        result = host
    elif ".".join(labels[-2:]) in _MULTI_LABEL_SUFFIXES and len(labels) >= 3:
        result = ".".join(labels[-3:])
    else:
        result = ".".join(labels[-2:])
    return result[4:] if result.startswith("www.") else result


def is_in_scope(url: str, scope_domains: list[str]) -> bool:
    """URL 主机是否等于或落在任一限定域名之下。"""
    host = (urlparse(url).hostname or "").lower()
    if not host:
        return False
    for scope in scope_domains:
        scope = scope.strip().lower().lstrip(".")
        if not scope:
            continue
        if host == scope or host.endswith("." + scope):
            return True
    return False


def safe_filename(url: str) -> str:
    path = urlparse(url).path
    name = unquote(path.rsplit("/", 1)[-1])
    name = re.sub(r"[^\w.\-一-鿿]+", "_", name).strip("_")
    return name[:180] or "unnamed"
