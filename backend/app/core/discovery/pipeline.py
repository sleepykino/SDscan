"""T2 两阶段编排：provider 遍历、断点续跑、证据归并、DNS 验活、WS 事件。

由 scheduler 调用；暂停/取消复用 scheduler 的 RunControl（鸭子类型：
cancelled 属性 + running_gate 事件）。
"""
from __future__ import annotations

import asyncio
from datetime import datetime

from sqlalchemy import func, select

from ...config import load_settings
from ...models import DomainList, T2ProviderRun, Task
from ...ws.manager import manager
from ..rule_engine import split_lines
from . import registry
from .base import PROVIDER_LABELS, STAGE_APEX, STAGE_SUB, ProviderContext, ProviderSkipped
from .dns import verify_many
from .merge import normalize_domain, upsert_apex, upsert_sub


class T2Pipeline:

    # ------------------------------------------------------------- 入口
    async def run_apex(self, task_id: int, ctrl) -> None:
        await self._run_stage(task_id, ctrl, STAGE_APEX)

    async def run_subs(self, task_id: int, ctrl) -> None:
        await self._run_stage(task_id, ctrl, STAGE_SUB)

    # ------------------------------------------------------------- 公共工具
    async def _emit(self, task_id: int, event: dict) -> None:
        event.setdefault("ts", datetime.now().strftime("%H:%M:%S"))
        await manager.broadcast(task_id, event)

    async def _log(self, task_id: int, message: str, cls: str = "") -> None:
        await self._emit(task_id, {"type": "log", "message": message, "cls": cls})

    async def _wait_gate(self, ctrl) -> None:
        gate = getattr(ctrl, "running_gate", None)
        if gate is not None:
            while not gate.is_set() and not ctrl.cancelled:
                await gate.wait()

    def _get_run(self, db, task_id: int, stage: str, provider: str,
                 target: str) -> T2ProviderRun:
        row = db.execute(
            select(T2ProviderRun).where(
                T2ProviderRun.task_id == task_id,
                T2ProviderRun.stage == stage,
                T2ProviderRun.provider == provider,
                T2ProviderRun.target == target,
            )
        ).scalar_one_or_none()
        if row is None:
            row = T2ProviderRun(
                task_id=task_id, stage=stage, provider=provider,
                target=target, status="pending",
            )
            db.add(row)
            db.flush()
        return row

    async def _emit_run(self, task_id: int, row: T2ProviderRun) -> None:
        await self._emit(task_id, {
            "type": "provider_status",
            "run": {
                "id": row.id, "stage": row.stage, "provider": row.provider,
                "target": row.target, "status": row.status,
                "error_msg": row.error_msg, "stats": row.stats or {},
                "display_name": PROVIDER_LABELS.get(row.provider, row.provider),
            },
        })

    def _stats(self, db, task_id: int) -> dict:
        def count(where) -> int:
            return db.scalar(
                select(func.count(DomainList.id)).where(
                    DomainList.task_id == task_id, *where
                )
            ) or 0

        apex = count([DomainList.layer == "apex"])
        sub = count([DomainList.layer == "sub"])
        runs = list(db.execute(
            select(T2ProviderRun).where(T2ProviderRun.task_id == task_id)
        ).scalars())
        return {
            "total": len(runs),
            "done": sum(r.status == "done" for r in runs),
            "failed": sum(r.status == "failed" for r in runs),
            "skipped": sum(r.status == "skipped" for r in runs),
            "running": sum(r.status == "running" for r in runs),
            "pending": sum(r.status == "pending" for r in runs),
            "apex_total": apex,
            "apex_confirmed": count([
                DomainList.layer == "apex", DomainList.status == "confirmed"
            ]),
            "apex_rejected": count([
                DomainList.layer == "apex", DomainList.status == "rejected"
            ]),
            "sub_total": sub,
            "sub_alive": count([
                DomainList.layer == "sub", DomainList.alive.is_(True)
            ]),
            "domains": apex + sub,
            "results": 0, "hits": 0, "attachments": 0, "blocked": 0,
            "providers_done": sum(r.status == "done" for r in runs),
            "providers_failed": sum(r.status == "failed" for r in runs),
            "providers_skipped": sum(r.status == "skipped" for r in runs),
        }

    async def _push_stats(self, db, task: Task) -> None:
        stats = self._stats(db, task.id)
        task.stats = stats
        db.commit()
        await self._emit(task.id, {"type": "stats", "stats": stats})

    # ------------------------------------------------------------- 阶段主流程
    async def _run_stage(self, task_id: int, ctrl, stage: str) -> None:
        from ...database import SessionLocal

        settings = load_settings()
        db = SessionLocal()
        try:
            task = db.get(Task, task_id)
            if task is None:
                return
            task.status = "running"
            task.started_at = task.started_at or datetime.now()
            task.error_msg = ""
            db.commit()

            aliases = split_lines(task.keywords)
            codes = registry.selected_codes(stage, task.params or {}, settings)
            await self._log(
                task_id,
                f"> T2 {stage} 启动：{len(codes)} 个数据源（{', '.join(codes) or '无'}）",
            )

            if stage == STAGE_APEX:
                ok = await self._run_apex_providers(db, task, ctrl, settings, codes, aliases)
                await self._finish_apex(db, task, ctrl, ok)
            else:
                await self._run_sub_providers(db, task, ctrl, settings, codes)
                await self._finish_subs(db, task, ctrl)
        except Exception as exc:
            db.rollback()
            task = db.get(Task, task_id)
            if task and task.status != "done":
                task.status = "failed"
                task.error_msg = f"T2 调度异常：{exc}"
                task.finished_at = datetime.now()
                db.commit()
            await self._emit(task_id, {"type": "task_done", "status": "failed",
                                       "error": str(exc)})
        finally:
            db.close()

    # ---------------- 阶段 A
    async def _run_apex_providers(self, db, task, ctrl, settings, codes,
                                  aliases) -> bool:
        """返回是否至少一个 provider 正常完成（done）。"""
        any_done = False
        for code in codes:
            if ctrl.cancelled:
                break
            await self._wait_gate(ctrl)
            run = self._get_run(db, task.id, STAGE_APEX, code, "")
            if run.status == "done":
                await self._log(task.id, f"> [{code}] 已完成，断点跳过")
                any_done = True
                continue

            provider = registry.get_provider(code)
            if not settings.get("t2_apex_enabled", {}).get(code, True):
                run.status, run.error_msg = "skipped", "已在设置中停用"
                db.commit()
                await self._emit_run(task.id, run)
                continue
            if not provider.is_configured(settings):
                run.status, run.error_msg = "skipped", "未配置 Key 或缺少前置条件"
                db.commit()
                await self._emit_run(task.id, run)
                await self._log(task.id, f"> [{code}] 跳过：{run.error_msg}")
                continue

            ctx = ProviderContext(
                task=task, settings=settings, stage=STAGE_APEX,
                emit=lambda ev: self._emit(task.id, ev),
                cancelled=lambda: ctrl.cancelled,
                aliases=aliases,
                http_timeout=float(settings.get("t2_passive_timeout", 15)),
                max_pages=int((task.params or {}).get("engine_max_pages")
                              or settings.get("t2_engine_max_pages", 2)),
                se_platform_ids=list((task.params or {}).get("se_platform_ids") or []),
                se_max_pages=int((task.params or {}).get("se_max_pages") or task.max_pages or 1),
            )

            run.status, run.error_msg = "running", ""
            db.commit()
            await self._emit_run(task.id, run)
            produced = 0
            try:
                async for result in provider.run(ctx):
                    await self._wait_gate(ctrl)
                    if ctrl.cancelled:
                        break
                    if not normalize_domain(result.domain):
                        await self._log(
                            task.id,
                            f"> [{code}] 跳过无法识别为主域的结果：{result.domain!r}",
                        )
                        continue
                    row, evidence, is_new = upsert_apex(
                        db, task, result.domain, result.evidence, aliases
                    )
                    db.commit()
                    produced += 1
                    if is_new:
                        await self._emit(task.id, {
                            "type": "domain",
                            "domain": self._domain_payload(row),
                        })
                    if evidence is not None:
                        await self._emit(task.id, {
                            "type": "domain_evidence",
                            "domain_id": row.id,
                            "evidence": self._evidence_payload(evidence),
                        })
            except ProviderSkipped as exc:
                run.status, run.error_msg = "skipped", str(exc)[:500]
                await self._log(task.id, f"> [{code}] 跳过：{exc}")
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001 单 provider 失败不阻断
                run.status, run.error_msg = "failed", str(exc)[:500]
                await self._log(task.id, f"x [{code}] 失败：{exc}", "log-err")
            else:
                run.status, run.error_msg = "done", ""
                any_done = True
            run.stats = {"produced": produced}
            db.commit()
            await self._emit_run(task.id, run)
            await self._push_stats(db, task)
            if not ctrl.cancelled:
                await asyncio.sleep(min(task.request_interval, 2.0))
        return any_done

    async def _finish_apex(self, db, task, ctrl, any_done: bool) -> None:
        stats = self._stats(db, task.id)
        task.finished_at = datetime.now()
        task.stats = stats
        if ctrl.cancelled:
            task.status = "failed"
            task.error_msg = "用户取消"
            db.commit()
            await self._emit(task.id, {"type": "task_done", "status": "failed",
                                        "error": "用户取消"})
            return
        apex_rows = list(db.execute(
            select(DomainList).where(
                DomainList.task_id == task.id, DomainList.layer == "apex"
            )
        ).scalars())
        if not apex_rows and not any_done:
            task.status = "failed"
            task.error_msg = "所选数据源全部跳过或失败，未获取到主域名"
            db.commit()
            await self._emit(task.id, {
                "type": "task_done", "status": "failed",
                "error": task.error_msg,
            })
            return
        if not apex_rows:
            task.status = "done"
            db.commit()
            await self._emit(task.id, {"type": "task_done", "status": "done",
                                        "stats": stats})
            await self._log(task.id, "> 所有数据源均无主域结果，任务结束")
            return
        task.status = "await_gate"
        db.commit()
        await self._emit(task.id, {"type": "stats", "stats": stats})
        gate_payload = {
            "apex_total": stats["apex_total"],
            "high": sum(r.confidence == "high" for r in apex_rows),
            "medium": sum(r.confidence == "medium" for r in apex_rows),
            "low": sum(r.confidence == "low" for r in apex_rows),
        }
        await self._emit(task.id, {"type": "t2_gate", **gate_payload})
        await self._log(
            task.id,
            f"> 阶段A 结束：{gate_payload['apex_total']} 个候选主域"
            f"（高 {gate_payload['high']}/中 {gate_payload['medium']}/低 {gate_payload['low']}），"
            "请在域名清单中确认后再枚举子域",
            "log-warn",
        )

    # ---------------- 阶段 B
    async def _run_sub_providers(self, db, task, ctrl, settings, codes) -> None:
        apex_rows = list(db.execute(
            select(DomainList).where(
                DomainList.task_id == task.id,
                DomainList.layer == "apex",
                DomainList.status == "confirmed",
            ).order_by(DomainList.id)
        ).scalars())
        if not apex_rows:
            raise RuntimeError("没有已确认的主域名，无法枚举子域")

        for apex_row in apex_rows:
            apex = apex_row.domain
            if ctrl.cancelled:
                break
            await self._log(task.id, f"> 开始枚举主域 {apex} 的子域名")
            for code in codes:
                if ctrl.cancelled:
                    break
                await self._wait_gate(ctrl)
                run = self._get_run(db, task.id, STAGE_SUB, code, apex)
                if run.status == "done":
                    await self._log(task.id, f"> [{code}/{apex}] 已完成，断点跳过")
                    continue
                provider = registry.get_provider(code)
                if not settings.get("t2_sub_enabled", {}).get(code, True):
                    run.status, run.error_msg = "skipped", "已在设置中停用"
                    db.commit()
                    await self._emit_run(task.id, run)
                    continue
                if not provider.is_configured(settings):
                    run.status, run.error_msg = "skipped", "未配置 Key 或缺少前置条件"
                    db.commit()
                    await self._emit_run(task.id, run)
                    await self._log(task.id, f"> [{code}] 跳过：{run.error_msg}")
                    continue

                ctx = ProviderContext(
                    task=task, settings=settings, stage=STAGE_SUB, target=apex,
                    emit=lambda ev: self._emit(task.id, ev),
                    cancelled=lambda: ctrl.cancelled,
                    aliases=[],
                    http_timeout=float(settings.get("t2_passive_timeout", 15)),
                    max_pages=int((task.params or {}).get("engine_max_pages")
                                  or settings.get("t2_engine_max_pages", 2)),
                )
                run.status, run.error_msg = "running", ""
                db.commit()
                await self._emit_run(task.id, run)
                produced = 0
                try:
                    async for sub in provider.run(ctx, apex):
                        await self._wait_gate(ctrl)
                        if ctrl.cancelled:
                            break
                        row, evidence, is_new = upsert_sub(
                            db, task, sub.host, apex, sub.evidence
                        )
                        db.commit()
                        produced += 1
                        if is_new:
                            await self._emit(task.id, {
                                "type": "domain",
                                "domain": self._domain_payload(row),
                            })
                        if evidence is not None:
                            await self._emit(task.id, {
                                "type": "domain_evidence",
                                "domain_id": row.id,
                                "evidence": self._evidence_payload(evidence),
                            })
                except ProviderSkipped as exc:
                    run.status, run.error_msg = "skipped", str(exc)[:500]
                    await self._log(task.id, f"> [{code}] 跳过：{exc}")
                except asyncio.CancelledError:
                    raise
                except Exception as exc:  # noqa: BLE001
                    run.status, run.error_msg = "failed", str(exc)[:500]
                    await self._log(task.id, f"x [{code}/{apex}] 失败：{exc}", "log-err")
                else:
                    run.status = "done"
                run.stats = {"produced": produced}
                db.commit()
                await self._emit_run(task.id, run)
                await self._push_stats(db, task)
                if not ctrl.cancelled:
                    await asyncio.sleep(min(task.request_interval, 2.0))

            # 该主域的子域 DNS 验活（仅对未验活的行）
            await self._verify_apex_subs(db, task, apex, ctrl)

    async def _verify_apex_subs(self, db, task, apex: str, ctrl) -> None:
        rows = list(db.execute(
            select(DomainList).where(
                DomainList.task_id == task.id,
                DomainList.layer == "sub",
                DomainList.parent_domain == apex,
                DomainList.alive.is_(None),
            )
        ).scalars())
        if not rows:
            return
        await self._log(task.id, f"> DNS 验活 {len(rows)} 个子域（仅 DNS 查询）")
        settings = load_settings()
        result = await verify_many(
            [r.domain for r in rows],
            timeout=float(settings.get("t2_dns_timeout", 5)),
            concurrency=20,
        )
        for row in rows:
            ips = result.get(row.domain, [])
            row.alive = bool(ips)
            row.resolved_ip = ",".join(ips[:4])
        db.commit()
        for row in rows:
            await self._emit(task.id, {
                "type": "domain", "domain": self._domain_payload(row),
            })

    async def _finish_subs(self, db, task, ctrl) -> None:
        stats = self._stats(db, task.id)
        task.finished_at = datetime.now()
        task.stats = stats
        if ctrl.cancelled:
            task.status = "failed"
            task.error_msg = "用户取消"
            db.commit()
            await self._emit(task.id, {"type": "task_done", "status": "failed",
                                        "error": "用户取消"})
            return
        task.status = "done"
        db.commit()
        await self._emit(task.id, {"type": "stats", "stats": stats})
        await self._emit(task.id, {"type": "task_done", "status": "done",
                                    "stats": stats})
        await self._log(
            task.id,
            f"> 阶段B 结束：共 {stats['sub_total']} 个子域，存活 {stats['sub_alive']}",
        )

    # ------------------------------------------------------------- 载荷
    @staticmethod
    def _domain_payload(row: DomainList) -> dict:
        return {
            "id": row.id,
            "domain": row.domain,
            "layer": row.layer,
            "parent_domain": row.parent_domain,
            "provider": row.provider,
            "confidence": row.confidence,
            "status": row.status,
            "alive": row.alive,
            "resolved_ip": row.resolved_ip,
            "unit_name": row.unit_name,
        }

    @staticmethod
    def _evidence_payload(ev) -> dict:
        return {
            "provider": ev.provider,
            "stage": ev.stage,
            "icp_no": ev.icp_no,
            "icp_unit": ev.icp_unit,
            "site_name": ev.site_name,
            "cert_org": ev.cert_org,
            "ref_url": ev.ref_url,
        }


t2_pipeline = T2Pipeline()
