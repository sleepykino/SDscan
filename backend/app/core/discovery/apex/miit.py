"""工信部 ICP 备案 provider（有头半自动）。

流程：打开 beian.miit.gov.cn 有头窗口 → WS 通知前端 → 用户自行查询
（输入单位全称、完成滑块、点查询，看到结果列表）→ 用户在界面点「已完成查询」
→ provider 在结果列表逐行点「详情」读取网站域名（页面内视图切换，非弹窗），
→ 自动翻页 → 关闭窗口、持久化 Cookie。

页面结构（2026-09-28 实测，站点改版时校准本文件选择器）：
- 结果列表：``div.listcont .el-table__body-wrapper tbody tr.el-table__row``
  列：序号 / 主办单位名称 / 主办单位性质 / 服务备案号 / 审核日期 / 操作(详情按钮)
- 详情：点「详情」后 ``div.contlist > div.details`` 由隐藏变可见，
  内含两个 ``div.tableA`` 卡：主体信息 + 服务信息，域名在「网站域名：」行
- 返回：``div.details_close button``「返回查询结果」
- 分页：Element 分页 ``.el-pagination .btn-next``
"""
from __future__ import annotations

import asyncio
import re
from typing import AsyncIterator, Any

from ....config import load_settings, save_settings
from ...engine.web_collector import web_collector
from ...rule_engine import registrable_domain
from ..base import ApexResult, Evidence, ProviderContext, ProviderSkipped
from ..merge import ICP_NO_RE, normalize_name

MIIT_URL = "https://beian.miit.gov.cn/"
MAX_PAGES = 20

# task_id -> {"event": Event, "cancel": bool}：API 端点在用户操作时 set
solve_events: dict[int, dict] = {}

# ---- 页面选择器（站点改版时只需改这里） ---------------------------------
LIST_ROWS = "div.listcont .el-table__body-wrapper tbody tr.el-table__row"
DETAIL_CARDS_JS = """
() => {
  const details = [...document.querySelectorAll('div.contlist > div.details')];
  const d = details.find((el) => {
    const s = el.getAttribute('style') || '';
    return !/display\\s*:\\s*none/.test(s);
  });
  if (!d) return null;
  return [...d.querySelectorAll('div.tableA')].map((c) => c.innerText || '');
}
"""
DETAIL_VISIBLE_JS = """
() => {
  const details = [...document.querySelectorAll('div.contlist > div.details')];
  return details.some((el) => !/display\\s*:\\s*none/.test(el.getAttribute('style') || ''));
}
"""
# 详情卡片异步加载：等待「网站域名」字段渲染
DETAIL_READY_JS = """
() => {
  const details = [...document.querySelectorAll('div.contlist > div.details')];
  const d = details.find((el) => !/display\\s*:\\s*none/.test(el.getAttribute('style') || ''));
  if (!d) return false;
  return (d.innerText || '').includes('网站域名');
}
"""
BACK_BUTTON = "div.details_close button"
NEXT_PAGE = ".el-pagination .btn-next"

_DOMAIN_FIELD_RE = re.compile(r"网站域名[：:]\s*([^\n]+)")
_ICP_FIELD_RE = re.compile(r"ICP备案/许可证号[：:]\s*([^\n]+)")
_DATE_FIELD_RE = re.compile(r"审核通过日期[：:]\s*([^\n]+)")
_UNIT_FIELD_RE = re.compile(r"主办单位名称[：:]\s*([^\n]+)")
_KIND_FIELD_RE = re.compile(r"主办单位性质[：:]\s*([^\n]+)")


def mark_done(task_id: int) -> None:
    slot = solve_events.get(task_id)
    if slot is not None:
        slot["cancel"] = False
        slot["event"].set()


def mark_cancel(task_id: int) -> None:
    slot = solve_events.get(task_id)
    if slot is not None:
        slot["cancel"] = True
        slot["event"].set()


def _first(pattern: re.Pattern[str], *texts: str) -> str:
    for text in texts:
        m = pattern.search(text or "")
        if m:
            return m.group(1).strip()
    return ""


def _parse_detail(subject_card: str, service_card: str,
                  row_cells: list[str], unit_name: str) -> dict | None:
    """从两张信息卡文本中解析域名；无域名返回 None。"""
    raw_domain = _first(_DOMAIN_FIELD_RE, service_card)
    # 逐 token 归一化为注册主域：IP、空占位（--/无）、非法值一律丢弃
    domains: list[str] = []
    for token in re.split(r"[\s,;，；、]+", raw_domain):
        token = token.strip().lower().strip(".")
        if not token or token in {"-", "--", "无", "暂无", "null", "none"}:
            continue
        reg = registrable_domain(token)
        if reg:
            domains.append(reg)
    if not domains:
        return None

    service_no = _first(_ICP_FIELD_RE, service_card)
    subject_no = _first(_ICP_FIELD_RE, subject_card)
    icp_unit = _first(_UNIT_FIELD_RE, subject_card) or (
        row_cells[1] if len(row_cells) > 1 else ""
    ) or unit_name
    kind = _first(_KIND_FIELD_RE, subject_card) or (
        row_cells[2] if len(row_cells) > 2 else ""
    )
    verify_date = _first(_DATE_FIELD_RE, subject_card) or (
        row_cells[4] if len(row_cells) > 4 else ""
    )
    icp_match = ICP_NO_RE.search(service_no.replace(" ", "")) or ICP_NO_RE.search(
        subject_no.replace(" ", "")
    )
    return {
        "domains": list(dict.fromkeys(domains)),
        "icp_no": icp_match.group(0) if icp_match else service_no or subject_no,
        "icp_unit": icp_unit,
        "kind": kind,
        "verify_date": verify_date,
        "service_no": service_no or subject_no,
    }


class MiitApex:
    code = "miit"
    display_name = "工信部ICP备案"

    def is_configured(self, settings: dict) -> bool:
        return bool(settings.get("t2_apex_enabled", {}).get("miit", True))

    async def run(self, ctx: ProviderContext) -> AsyncIterator:
        task_id = ctx.task.id
        slot = solve_events.get(task_id)
        if slot is None:
            slot = {"event": asyncio.Event(), "cancel": False}
            solve_events[task_id] = slot
        slot["event"].clear()
        slot["cancel"] = False

        await ctx.log(
            "> [miit] 已打开工信部备案查询窗口：请输入单位全称、完成滑块并点查询，"
            "看到结果列表后点「已完成查询」"
        )
        try:
            await web_collector.start_solve(MIIT_URL)
        except RuntimeError as exc:
            raise ProviderSkipped(f"无法打开查询窗口：{exc}") from exc

        await ctx.emit({"type": "provider_need_solve", "provider": "miit",
                        "task_id": task_id})

        page: Any = None
        try:
            await slot["event"].wait()
            if slot["cancel"]:
                raise ProviderSkipped("用户取消了工信部查询")
            if ctx.cancelled():
                raise ProviderSkipped("任务已取消")

            page = web_collector.solve_page
            if page is None:
                raise ProviderSkipped("查询窗口已关闭")

            parsed = await self._collect_all_pages(ctx, page)

            cookie = await web_collector.finish_solve()
        finally:
            if web_collector.solve_page is not None:
                try:
                    await web_collector.cancel_solve()
                except Exception:
                    pass
            solve_events.pop(task_id, None)

        if cookie:
            settings = load_settings()
            settings["miit_cookie"] = cookie
            save_settings(settings)

        await ctx.log(f"> [miit] 共读取 {len(parsed)} 条服务备案")
        seen: set[str] = set()
        for item in parsed:
            for domain in item["domains"]:
                if domain in seen:
                    continue
                seen.add(domain)
                yield self._make_result(domain, item)

    # ------------------------------------------------------------------ #
    async def _collect_all_pages(self, ctx: ProviderContext, page) -> list[dict]:
        # 用户可能停在某条详情视图：先尝试回到列表
        await self._back_to_list(page)

        rows_locator = page.locator(LIST_ROWS)
        try:
            await rows_locator.first.wait_for(state="visible", timeout=8000)
        except Exception:
            empty = await self._has_empty_result(page)
            raise ProviderSkipped(
                "未在页面上检测到结果列表（请确认已点查询且列表已加载）"
                if not empty else "查询结果为空（无备案记录）"
            )

        results: list[dict] = []
        for page_no in range(1, MAX_PAGES + 1):
            if ctx.cancelled():
                break
            count = await page.locator(LIST_ROWS).count()
            page_items = 0
            empty_streak = 0
            for idx in range(count):
                if ctx.cancelled():
                    break
                item = await self._read_one_row(ctx, page, idx)
                if item:
                    results.append(item)
                    page_items += 1
                    empty_streak = 0
                else:
                    empty_streak += 1
                    if empty_streak == 3:
                        await ctx.log(
                            "> [miit] 连续 3 行未取到域名：可能是验证码会话已失效，"
                            "请重新查询后再点「已完成查询」",
                            "log-warn",
                        )
            await ctx.log(f"> [miit] 第 {page_no} 页：{count} 行，含域名 {page_items} 条")

            if not await self._goto_next_page(page):
                break
        return results

    async def _read_one_row(self, ctx: ProviderContext, page, idx: int) -> dict | None:
        rows = page.locator(LIST_ROWS)
        row = rows.nth(idx)
        try:
            cells = await row.locator("td").all_inner_texts()
            cells = [c.strip() for c in cells]
        except Exception:
            return None
        service_hint = cells[3] if len(cells) > 3 else ""

        # 点该行「详情」
        detail_btn = row.locator("button", has_text="详情")
        if await detail_btn.count() == 0:
            detail_btn = row.locator("button").last
        try:
            await detail_btn.first.click(timeout=5000)
            await self._wait_detail_visible(page)
        except Exception as exc:
            await ctx.log(f"> [miit] 第 {idx + 1} 行详情打开失败：{exc}")
            return None

        try:
            cards = await page.evaluate(DETAIL_CARDS_JS)
        except Exception:
            cards = None
        item = None
        if cards:
            subject_card = cards[0] if len(cards) >= 1 else ""
            service_card = cards[1] if len(cards) >= 2 else ""
            item = _parse_detail(subject_card, service_card, cells, ctx.unit_name)
        if item is None:
            await ctx.log(
                f"> [miit] {service_hint or '第' + str(idx + 1) + '行'} 详情未取到网站域名"
            )
        await self._back_to_list(page)
        return item

    async def _wait_detail_visible(self, page) -> None:
        for _ in range(20):  # 最多 10s
            if await page.evaluate(DETAIL_VISIBLE_JS):
                # 详情接口异步渲染：等到「网站域名」字段出现（最多再等 6s）
                for _ in range(12):
                    if await page.evaluate(DETAIL_READY_JS):
                        await page.wait_for_timeout(300)
                        return
                    await page.wait_for_timeout(500)
                return  # 字段始终不出（可能该条无网站服务/会话失效），上层按空处理
            await page.wait_for_timeout(500)

    async def _back_to_list(self, page) -> None:
        btn = page.locator(BACK_BUTTON)
        if await btn.count() and await btn.first.is_visible():
            try:
                await btn.first.click(timeout=4000)
                await page.wait_for_timeout(700)
            except Exception:
                pass

    async def _has_empty_result(self, page) -> bool:
        try:
            txt = await page.locator(".el-table__empty-text").first.inner_text(timeout=2000)
            return "暂无数据" in (txt or "")
        except Exception:
            return False

    async def _goto_next_page(self, page) -> bool:
        """点击 Element 分页下一页；无下一页返回 False。"""
        btn = page.locator(NEXT_PAGE)
        if await btn.count() == 0:
            return False
        try:
            classes = await btn.first.get_attribute("class") or ""
            disabled = await btn.first.is_disabled()
        except Exception:
            return False
        if disabled or "is-disabled" in classes:
            return False
        try:
            before = await page.locator(LIST_ROWS).first.inner_text(timeout=1000)
        except Exception:
            before = ""
        try:
            await btn.first.click(timeout=4000)
        except Exception:
            return False
        # 等待首行文本变化（最多 8s），确认翻页生效
        for _ in range(16):
            await page.wait_for_timeout(500)
            try:
                now = await page.locator(LIST_ROWS).first.inner_text(timeout=1000)
            except Exception:
                now = ""
            if now and now != before:
                return True
        return True  # 点击成功但未检测到变化时不阻塞，由上层空页自然结束

    @staticmethod
    def _make_result(domain: str, item: dict) -> ApexResult:
        return ApexResult(
            domain=domain,
            evidence=Evidence(
                provider="miit",
                stage="apex",
                icp_no=item["icp_no"],
                icp_unit=item["icp_unit"],
                ref_url=MIIT_URL,
                detail={
                    "service_no": item["service_no"],
                    "company_type": item["kind"],
                    "verify_time": item["verify_date"],
                },
            ),
        )
