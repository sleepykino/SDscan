"""异步任务调度器。

核心职责（对应详细设计 §4/§9 与初始提示词 §九）：
- 关键词×平台×页码组合落库（task_unit），支持断点续跑、单组合最多重试 3 次；
- web/api 双通道顺序采集，Playwright 并发固定 1（通道内已加锁），同时全局只跑一个任务；
- 风控命中 → 仅阻塞当前平台、WebSocket 告警、等待人工过码后回填 Cookie 并续跑；
- 暂停 / 恢复 / 取消；
- T2 域名归集、T5 正文敏感核查、T3 附件下载解析等模板后处理。
"""
from __future__ import annotations

import asyncio
from datetime import datetime

from sqlalchemy import func, select

from ..config import load_settings
from ..models import (
    Attachment,
    DomainList,
    Platform,
    SearchResult,
    SensitiveHit,
    SensitiveRule,
    SyntaxDict,
    Task,
    TaskUnit,
)
from ..ws.manager import manager
from . import attachment as attachment_svc
from .engine.api_collector import ApiCollector
from .engine.base import FetchedPage
from .engine.risk import detect_risk
from .engine.web_collector import web_collector
from .rule_engine import (
    build_url,
    html_to_text,
    is_in_scope,
    page_offset,
    registrable_domain,
    safe_filename,
    split_lines,
    wrap_keyword,
)
from .sensitive import SensitiveMatcher

MAX_ATTEMPTS = 3


def recover_orphan_tasks() -> None:
    """服务重启后清理僵尸任务。

    上次进程中断时可能遗留 status=running 的任务（调度器内存实例已丢失），
    若不处理会永远无法取消也无法启动。此处统一复位为 failed，
    其 running 组合恢复 pending，配合断点续跑机制可重新启动。
    """
    from ..database import SessionLocal

    db = SessionLocal()
    try:
        orphans = list(
            db.execute(select(Task).where(Task.status == "running")).scalars()
        )
        for task in orphans:
            task.status = "failed"
            task.error_msg = "服务重启，任务已中断（可重新启动续跑）"
            task.finished_at = datetime.now()
            for unit in db.execute(
                select(TaskUnit).where(
                    TaskUnit.task_id == task.id, TaskUnit.status == "running"
                )
            ).scalars():
                unit.status = "pending"
                unit.error_msg = ""
        if orphans:
            db.commit()
    finally:
        db.close()


class RunControl:
    """单次运行的运行时控制信号。"""

    def __init__(self, task_id: int) -> None:
        self.task_id = task_id
        self.running_gate = asyncio.Event()
        self.running_gate.set()  # set=运行中，clear=人工暂停
        self.cancelled = False
        self.blocked: set[int] = set()
        self.unblock_events: dict[int, asyncio.Event] = {}

    def unblock(self, platform_id: int) -> None:
        self.blocked.discard(platform_id)
        event = self.unblock_events.pop(platform_id, None)
        if event is not None:
            event.set()

    def event_for(self, platform_id: int) -> asyncio.Event:
        if platform_id not in self.unblock_events:
            self.unblock_events[platform_id] = asyncio.Event()
        return self.unblock_events[platform_id]


class Scheduler:
    def __init__(self) -> None:
        self.runs: dict[int, RunControl] = {}
        self._api = ApiCollector()

    # ------------------------------------------------------------------ #
    # 对外控制
    # ------------------------------------------------------------------ #
    def running_task_id(self) -> int | None:
        return next(iter(self.runs), None)

    async def start(self, task_id: int) -> None:
        if self.runs:
            raise RuntimeError("已有任务在执行，本机单任务顺序调度")
        self._validate(task_id)
        ctrl = RunControl(task_id)
        self.runs[task_id] = ctrl
        asyncio.create_task(self._safe_run(task_id, ctrl))

    async def pause(self, task_id: int) -> None:
        ctrl = self.runs.get(task_id)
        if ctrl is None:
            return
        ctrl.running_gate.clear()

    async def resume(self, task_id: int) -> None:
        ctrl = self.runs.get(task_id)
        if ctrl is None:
            return
        ctrl.running_gate.set()

    async def cancel(self, task_id: int) -> bool:
        """发出取消信号并中断进行中的抓取。返回是否存在运行实例。"""
        ctrl = self.runs.get(task_id)
        if ctrl is None:
            return False
        ctrl.cancelled = True
        ctrl.running_gate.set()
        for event in list(ctrl.unblock_events.values()):
            event.set()
        # 强制关闭进行中的抓取页面，使 fetch 立即失败返回
        web_collector.close_pages_nowait()
        return True

    async def unblock_platform(self, task_id: int, platform_id: int) -> None:
        """人工过码完成后解除平台阻塞。"""
        ctrl = self.runs.get(task_id)
        if ctrl is not None:
            ctrl.unblock(platform_id)

    def blocked_platforms(self, task_id: int) -> list[int]:
        ctrl = self.runs.get(task_id)
        return sorted(ctrl.blocked) if ctrl else []

    # ------------------------------------------------------------------ #
    # 校验与组合初始化
    # ------------------------------------------------------------------ #
    def _validate(self, task_id: int) -> None:
        from ..database import SessionLocal

        db = SessionLocal()
        try:
            task = db.get(Task, task_id)
            if task is None:
                raise ValueError("任务不存在")
            if task.status not in ("pending", "failed", "paused_manual"):
                raise ValueError(f"任务状态 {task.status} 不可启动")
            if task.template_type == "T1" and not split_lines(task.keywords):
                raise ValueError("T1 关键词检索需要至少一个关键词")
            if task.template_type == "T2" and not (
                split_lines(task.keywords) or task.unit_name.strip()
            ):
                raise ValueError("T2 域名归集需要单位名称")
            if task.template_type in ("T3", "T4", "T5") and not split_lines(
                task.domain_scope
            ):
                raise ValueError(f"{task.template_type} 需要至少一个限定域名")
        finally:
            db.close()

    def _build_queries(self, db, task: Task) -> list[str]:
        """各模板实际送入搜索框的关键词（T3~T5 为语法包装串）。"""
        ttype = task.template_type
        if ttype == "T1":
            return split_lines(task.keywords)

        expression_row = (
            db.execute(
                select(SyntaxDict)
                .where(
                    SyntaxDict.template_type == ttype,
                    SyntaxDict.enabled.is_(True),
                )
                .order_by(SyntaxDict.id)
            )
            .scalars()
            .first()
        )
        expression = expression_row.expression if expression_row else ""

        if ttype == "T2":
            bases = split_lines(task.keywords) or [task.unit_name.strip()]
            return [wrap_keyword(expression, keyword=base) for base in bases]

        domains = split_lines(task.domain_scope)
        return [
            wrap_keyword(expression, domain=domain, keyword=task.unit_name.strip())
            for domain in domains
        ]

    def _ensure_units(self, db, task: Task, platforms: list[Platform]) -> list[tuple]:
        """生成有序组合 (platform_id, keyword, page)，并落库缺失的 unit。"""
        queries = self._build_queries(db, task)
        keys: list[tuple] = []
        existing = {
            (u.platform_id, u.keyword, u.page): u
            for u in db.execute(
                select(TaskUnit).where(TaskUnit.task_id == task.id)
            ).scalars()
        }
        for keyword in queries:
            for platform in platforms:
                page_count = 1 if platform.page_step == 0 else max(task.max_pages, 1)
                for page in range(1, page_count + 1):
                    key = (platform.id, keyword, page)
                    keys.append(key)
                    unit = existing.get(key)
                    if unit is None:
                        db.add(
                            TaskUnit(
                                task_id=task.id,
                                platform_id=platform.id,
                                keyword=keyword,
                                page=page,
                                status="pending",
                            )
                        )
                    elif unit.status in ("running", "failed") and unit.attempts < MAX_ATTEMPTS:
                        # 上次进程中断 / 可重试的失败，恢复为 pending
                        unit.status = "pending"
                        unit.error_msg = ""
        db.commit()
        return keys

    # ------------------------------------------------------------------ #
    # 主循环
    # ------------------------------------------------------------------ #
    async def _safe_run(self, task_id: int, ctrl: RunControl) -> None:
        try:
            await self._run(task_id, ctrl)
        except Exception as exc:  # 调度层兜底，任务置失败
            from ..database import SessionLocal

            db = SessionLocal()
            try:
                task = db.get(Task, task_id)
                if task and task.status != "done":
                    task.status = "failed"
                    task.error_msg = f"调度异常：{exc}"
                    task.finished_at = datetime.now()
                    db.commit()
            finally:
                db.close()
            await manager.broadcast(
                task_id, {"type": "task_done", "status": "failed", "error": str(exc)}
            )
        finally:
            self.runs.pop(task_id, None)

    async def _emit(self, task_id: int, event: dict) -> None:
        event.setdefault("ts", datetime.now().strftime("%H:%M:%S"))
        await manager.broadcast(task_id, event)

    async def _log(self, task_id: int, message: str) -> None:
        await self._emit(task_id, {"type": "log", "message": message})

    async def _wait_gate(self, ctrl: RunControl) -> None:
        """人工暂停点（暂停期间在此等待）。"""
        while not ctrl.running_gate.is_set() and not ctrl.cancelled:
            await ctrl.running_gate.wait()

    async def _run(self, task_id: int, ctrl: RunControl) -> None:
        from ..database import SessionLocal

        settings = load_settings()
        db = SessionLocal()
        try:
            task = db.get(Task, task_id)
            platform_ids = task.platform_ids or []
            plat_query = select(Platform).where(Platform.enabled.is_(True))
            if platform_ids:
                plat_query = plat_query.where(Platform.id.in_(platform_ids))
            platforms = list(db.execute(plat_query.order_by(Platform.id)).scalars())
            if not platforms:
                raise ValueError("没有可用的已启用平台")
            platform_map = {p.id: p for p in platforms}

            rules = list(
                db.execute(
                    select(SensitiveRule).where(SensitiveRule.enabled.is_(True))
                ).scalars()
            )
            matcher = SensitiveMatcher(rules)

            # 搜索引擎/平台自身域名，T2 归集时过滤
            generic_hosts = {
                registrable_domain(p.url_template)
                for p in db.execute(select(Platform)).scalars()
            }
            generic_hosts.discard("")
            generic_hosts |= {"zhihu.com", "weibo.com", "bilibili.com"}

            keys = self._ensure_units(db, task, platforms)
            task.status = "running"
            task.started_at = datetime.now()
            task.error_msg = ""
            stats = self._stats(db, task)
            task.stats = stats
            db.commit()

            await self._emit(task_id, {"type": "stats", "stats": stats})
            await self._log(
                task_id,
                f"> 任务启动：{task.template_type}，{len(keys)} 个组合，"
                f"{len(platforms)} 个平台，间隔 {task.request_interval}s",
            )

            scope_domains = split_lines(task.domain_scope)
            existing_results = {
                (r.platform_id, r.url)
                for r in db.execute(
                    select(SearchResult.platform_id, SearchResult.url).where(
                        SearchResult.task_id == task_id
                    )
                ).all()
            }

            for platform_id, keyword, logical_page in keys:
                if ctrl.cancelled:
                    break
                await self._wait_gate(ctrl)
                platform = platform_map[platform_id]

                unit = db.execute(
                    select(TaskUnit).where(
                        TaskUnit.task_id == task_id,
                        TaskUnit.platform_id == platform_id,
                        TaskUnit.keyword == keyword,
                        TaskUnit.page == logical_page,
                    )
                ).scalar_one()

                if unit.status == "done":
                    continue
                if platform_id in ctrl.blocked:
                    if unit.status != "blocked":
                        unit.status = "blocked"
                        db.commit()
                        await self._emit_unit(unit, platform.name)
                    continue

                page_value = page_offset(platform, logical_page)
                if page_value is None:
                    unit.status = "done"
                    unit.searched_at = datetime.now()
                    db.commit()
                    continue
                url = build_url(platform.url_template, keyword, page_value)

                # 单组合重试循环
                while True:
                    if ctrl.cancelled:
                        break
                    await self._wait_gate(ctrl)

                    unit.status = "running"
                    unit.attempts += 1
                    unit.error_msg = ""
                    db.commit()
                    await self._emit_unit(unit, platform.name)
                    await self._log(
                        task_id,
                        f"> [{platform.name}] p{logical_page} 第{unit.attempts}次 "
                        f"{keyword[:40]}",
                    )

                    page_obj = await self._fetch(platform, url, settings)

                    if ctrl.cancelled:
                        # 取消：丢弃本次抓取（含被中断产生的 error），
                        # 单元复位 pending，避免任务结束后残留“执行中”
                        unit.status = "pending"
                        unit.error_msg = ""
                        db.commit()
                        await self._emit_unit(unit, platform.name)
                        break

                    if page_obj.error:
                        unit.error_msg = page_obj.error[:500]
                        if unit.attempts >= MAX_ATTEMPTS:
                            unit.status = "failed"
                            db.commit()
                            await self._emit_unit(unit, platform.name)
                            await self._log(
                                task_id,
                                f"x [{platform.name}] 失败（重试耗尽）：{unit.error_msg[:80]}",
                            )
                            break
                        unit.status = "pending"
                        db.commit()
                        await self._emit_unit(unit, platform.name)
                        await asyncio.sleep(min(2.0, task.request_interval))
                        continue

                    reason = detect_risk(page_obj, platform.risk_control_hints or {})
                    if reason:
                        await self._handle_risk(
                            db, task, unit, platform, page_obj, reason, ctrl, url
                        )
                        if ctrl.cancelled:
                            break
                        # 过码完成，阻塞组合已重置 pending，重新处理当前组合
                        unit = db.get(TaskUnit, unit.id)
                        unit.attempts = 0
                        continue

                    await self._process_success(
                        db=db,
                        task=task,
                        unit=unit,
                        platform=platform,
                        keyword=keyword,
                        page_obj=page_obj,
                        scope_domains=scope_domains,
                        matcher=matcher,
                        generic_hosts=generic_hosts,
                        existing_results=existing_results,
                        settings=settings,
                        ctrl=ctrl,
                    )
                    break

                # 统计与节流
                stats = self._stats(db, task)
                task.stats = stats
                db.commit()
                await self._emit(task_id, {"type": "stats", "stats": stats})
                if not ctrl.cancelled and platform_id not in ctrl.blocked:
                    await asyncio.sleep(task.request_interval)

            # 收尾
            task.finished_at = datetime.now()
            stats = self._stats(db, task)
            task.stats = stats
            if ctrl.cancelled:
                task.status = "failed"
                task.error_msg = "用户取消"
            elif stats.get("failed", 0) > 0 and stats.get("done", 0) == 0:
                task.status = "failed"
            else:
                task.status = "done"
            db.commit()
            await self._emit(task_id, {"type": "stats", "stats": stats})
            await self._emit(
                task_id,
                {
                    "type": "task_done",
                    "status": task.status,
                    "stats": stats,
                    "error": task.error_msg,
                },
            )
            await self._log(task_id, f"> 任务结束：{task.status}")
        finally:
            db.close()

    # ------------------------------------------------------------------ #
    # 抓取与风控
    # ------------------------------------------------------------------ #
    async def _fetch(self, platform: Platform, url: str, settings: dict) -> FetchedPage:
        if platform.channel_type == "api":
            headers = dict(platform.headers or {})
            token = settings.get("github_token", "")
            if token and platform.code.startswith("github"):
                headers.setdefault("Authorization", f"Bearer {token}")
            return await self._api.fetch(
                url,
                headers=headers,
                cookie=platform.cookie or "",
                timeout=float(settings.get("http_timeout", 20)),
            )
        return await web_collector.fetch(
            url,
            cookie=platform.cookie or "",
            extra_headers=dict(platform.headers or {}),
            timeout=float(settings.get("http_timeout", 20)),
        )

    async def _handle_risk(
        self, db, task, unit, platform, page_obj, reason, ctrl: RunControl, url: str
    ) -> None:
        ctrl.blocked.add(platform.id)
        web_collector.last_blocked_url[platform.id] = page_obj.url or url
        unit.status = "blocked"
        unit.error_msg = reason
        if page_obj.screenshot_path:
            unit.screenshot_path = page_obj.screenshot_path
        # 该平台其余未完成组合一并标记 blocked
        for other in db.execute(
            select(TaskUnit).where(
                TaskUnit.task_id == task.id,
                TaskUnit.platform_id == platform.id,
                TaskUnit.status.in_(["pending", "running"]),
            )
        ).scalars():
            other.status = "blocked"
            other.error_msg = "平台风控，等待人工过码"
        db.commit()

        await self._emit_unit(unit, platform.name)
        await self._emit(
            task.id,
            {
                "type": "risk_alert",
                "platform_id": platform.id,
                "platform": platform.name,
                "reason": reason,
                "url": web_collector.last_blocked_url[platform.id],
            },
        )
        await self._log(
            task.id, f"! [{platform.name}] 触发风控，仅暂停该平台，等待人工过码…"
        )

        event = ctrl.event_for(platform.id)
        while not event.is_set() and not ctrl.cancelled:
            await event.wait()

        if not ctrl.cancelled:
            for blocked_unit in db.execute(
                select(TaskUnit).where(
                    TaskUnit.task_id == task.id,
                    TaskUnit.platform_id == platform.id,
                    TaskUnit.status == "blocked",
                )
            ).scalars():
                blocked_unit.status = "pending"
                blocked_unit.error_msg = ""
                blocked_unit.attempts = 0
            db.commit()
            await self._log(task.id, f"> [{platform.name}] 过码完成，继续采集")

    # ------------------------------------------------------------------ #
    # 成功组合的处理
    # ------------------------------------------------------------------ #
    async def _process_success(self, *, db, task, unit, platform, keyword,
                               page_obj, scope_domains, matcher, generic_hosts,
                               existing_results, settings, ctrl) -> None:
        from .rule_engine import extract_items

        items = extract_items(page_obj, platform)
        unit.screenshot_path = page_obj.screenshot_path or unit.screenshot_path
        await self._log(task.id, f"> [{platform.name}] 提取 {len(items)} 条结果")

        new_results: list[SearchResult] = []
        for item in items:
            dedupe_key = (platform.id, item["url"])
            if dedupe_key in existing_results:
                continue
            existing_results.add(dedupe_key)
            external = (
                None
                if not scope_domains
                else not is_in_scope(item["url"], scope_domains)
            )
            result = SearchResult(
                task_unit_id=unit.id,
                task_id=task.id,
                platform_id=platform.id,
                keyword=keyword,
                page=unit.page,
                title=item["title"][:500],
                url=item["url"][:2000],
                is_external=external,
                content_text=item.get("snippet", "")[:2000],
                screenshot_path=page_obj.screenshot_path or "",
            )
            db.add(result)
            db.flush()
            new_results.append(result)
            await self._emit(
                task.id,
                {
                    "type": "result",
                    "result": {
                        "id": result.id,
                        "platform": platform.name,
                        "keyword": keyword,
                        "page": unit.page,
                        "title": result.title,
                        "url": result.url,
                        "is_external": external,
                    },
                },
            )

        unit.status = "done"
        unit.searched_at = datetime.now()
        unit.error_msg = ""
        db.commit()
        await self._emit_unit(unit, platform.name)

        if task.template_type == "T2":
            await self._collect_domains(
                db, task, platform, new_results, generic_hosts
            )
        elif task.template_type == "T5":
            await self._content_check(
                db, task, platform, new_results, matcher, settings, ctrl
            )
            db.commit()
        elif task.template_type == "T3":
            await self._download_attachments(
                db, task, platform, new_results, matcher, settings
            )
            db.commit()

    async def _collect_domains(self, db, task, platform, results, generic_hosts) -> None:
        for result in results:
            domain = registrable_domain(result.url)
            if not domain or domain in generic_hosts:
                continue
            exists = db.execute(
                select(DomainList).where(
                    DomainList.task_id == task.id, DomainList.domain == domain
                )
            ).scalar_one_or_none()
            if exists:
                continue
            row = DomainList(
                task_id=task.id,
                unit_name=task.unit_name,
                domain=domain,
                source=f"{platform.name}｜{result.title[:60]}｜{result.url}",
                status="candidate",
            )
            db.add(row)
            db.commit()
            await self._emit(
                task.id,
                {"type": "domain", "domain": {"id": row.id, "domain": row.domain}},
            )

    async def _content_check(self, db, task, platform, results, matcher,
                             settings, ctrl) -> None:
        max_detail = int(
            (task.params or {}).get("t5_max_detail")
            or settings.get("t5_max_detail", 10)
        )
        for result in results[:max_detail]:
            if ctrl.cancelled:
                return
            detail = await web_collector.fetch(
                result.url,
                cookie=platform.cookie or "",
                save_screenshot=False,
            )
            if detail.error or not detail.html:
                continue
            # 跟随跳转后的最终 URL（如百度跳转链），并重新判定内外链
            if detail.url:
                result.url = detail.url[:2000]
                scope_domains = split_lines(task.domain_scope)
                if scope_domains:
                    result.is_external = not is_in_scope(detail.url, scope_domains)
            text = html_to_text(detail.html)
            result.content_text = text[:5000]
            await self._save_hits(db, task, matcher, text, source_type="page",
                                  source_url=result.url, result=result)
            db.commit()
            await asyncio.sleep(min(2.0, task.request_interval / 2))

    async def _download_attachments(self, db, task, platform, results, matcher,
                                    settings) -> None:
        limit = int(
            (task.params or {}).get("t3_download_limit")
            or settings.get("t3_download_limit", 20)
        )
        used = db.scalar(
            select(func.count(Attachment.id)).where(Attachment.task_id == task.id)
        ) or 0
        for result in results:
            if used >= limit:
                break
            ext = attachment_svc.attachment_ext(result.url)
            if not ext:
                continue
            used += 1
            row = Attachment(
                task_id=task.id,
                result_id=result.id,
                url=result.url[:2000],
                filename=safe_filename(result.url) or f"attachment.{ext}",
                file_type=ext,
                parse_status="pending",
            )
            db.add(row)
            db.commit()
            await self._emit(
                task.id, {"type": "attachment", "id": row.id, "status": "pending",
                          "filename": row.filename}
            )
            try:
                dest, ext_name, size = await attachment_svc.download(result.url)
            except Exception as exc:
                row.parse_status = "failed"
                row.error_msg = f"下载失败：{exc}"[:500]
                db.commit()
                continue
            # 相对 data/ 目录存储，下载接口据此定位文件
            row.file_path = f"attachments/{dest.name}"
            row.size = size
            status, text_or_err = attachment_svc.parse_text(dest, ext_name)
            row.parse_status = status
            if status == "parsed" and text_or_err:
                await self._save_hits(
                    db, task, matcher, text_or_err, source_type="attachment",
                    source_url=result.url, attachment=row
                )
            elif status == "failed":
                row.error_msg = text_or_err[:500]
            db.commit()
            await self._emit(
                task.id, {"type": "attachment", "id": row.id,
                          "status": row.parse_status, "filename": row.filename}
            )

    async def _save_hits(self, db, task, matcher: SensitiveMatcher, text: str, *,
                         source_type: str, source_url: str,
                         result=None, attachment=None) -> None:
        for rule, raw in matcher.find(text):
            hit = SensitiveHit(
                rule_id=rule.id,
                level=rule.level,
                category=rule.category,
                source_type=source_type,
                source_url=source_url[:2000],
                matched_text=matcher.desensitize(rule, raw),
                result_id=result.id if result else None,
                attachment_id=attachment.id if attachment else None,
                task_id=task.id,
            )
            db.add(hit)
            db.flush()
            await self._emit(
                task.id,
                {
                    "type": "hit",
                    "hit": {
                        "id": hit.id,
                        "level": rule.level,
                        "category": rule.category,
                        "name": rule.name,
                        "matched_text": hit.matched_text,
                        "source_type": source_type,
                    },
                },
            )

    # ------------------------------------------------------------------ #
    # 统计与事件
    # ------------------------------------------------------------------ #
    def _stats(self, db, task: Task) -> dict:
        def unit_count(status: str) -> int:
            return db.scalar(
                select(func.count(TaskUnit.id)).where(
                    TaskUnit.task_id == task.id, TaskUnit.status == status
                )
            ) or 0

        return {
            "total": db.scalar(
                select(func.count(TaskUnit.id)).where(TaskUnit.task_id == task.id)
            ) or 0,
            "done": unit_count("done"),
            "failed": unit_count("failed"),
            "blocked": unit_count("blocked"),
            "running": unit_count("running"),
            "pending": unit_count("pending"),
            "results": db.scalar(
                select(func.count(SearchResult.id)).where(
                    SearchResult.task_id == task.id
                )
            ) or 0,
            "hits": db.scalar(
                select(func.count(SensitiveHit.id)).where(SensitiveHit.task_id == task.id)
            ) or 0,
            "attachments": db.scalar(
                select(func.count(Attachment.id)).where(Attachment.task_id == task.id)
            ) or 0,
            "domains": db.scalar(
                select(func.count(DomainList.id)).where(DomainList.task_id == task.id)
            ) or 0,
        }

    async def _emit_unit(self, unit: TaskUnit, platform_name: str) -> None:
        await self._emit(
            unit.task_id,
            {
                "type": "unit_status",
                "unit": {
                    "id": unit.id,
                    "platform_id": unit.platform_id,
                    "platform": platform_name,
                    "keyword": unit.keyword,
                    "page": unit.page,
                    "status": unit.status,
                    "attempts": unit.attempts,
                    "error_msg": unit.error_msg,
                    "screenshot_path": unit.screenshot_path,
                },
            },
        )


scheduler = Scheduler()
