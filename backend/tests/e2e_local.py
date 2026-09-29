"""本地端到端联调（不依赖外网）。

启动本机 fixture 站点 + 真实后端（python run.py），覆盖：
- T1 web 通道全链路（选择器提取、截图、结果落库、断点取消后继续）
- T2 域名归集候选
- T3 附件下载解析（xlsx）+ 附件级敏感命中
- T5 正文跟进 + 页面级敏感命中
- 风控检测（风险关键词页面 → blocked + risk_alert WS 事件）
- WebSocket 事件、Excel 导出、规则正则校验

运行（在 backend/ 目录）：
    python tests/e2e_local.py
"""
from __future__ import annotations

import asyncio
import json
import os
import socket
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import httpx
import websockets

# 后端端口可用环境变量覆盖，避免与正在运行的实例冲突（共享同一 data 目录）
BACKEND_PORT = int(os.environ.get("SDSCAN_E2E_PORT", "8000"))
BACKEND = f"http://127.0.0.1:{BACKEND_PORT}"
FIXTURE_PORT = 18080
FIXTURE = f"http://127.0.0.1:{FIXTURE_PORT}"
VENV_PY = str(Path(__file__).resolve().parents[2] / ".venv" / "Scripts" / "python.exe")

ARTIFACT_DIR = Path(__file__).resolve().parent / "_e2e_artifacts"
ARTIFACT_DIR.mkdir(exist_ok=True)

SEARCH_HTML = """<!DOCTYPE html><html><head><title>示范搜索</title></head><body>
<div class="r"><h3><a href="http://127.0.0.1:{port}/detail/1">示范单位内部运维平台</a></h3></div>
<div class="r"><h3><a href="http://www.demo-unit.gov.cn/news/2">示范单位官方门户新闻</a></h3></div>
<div class="r"><h3><a href="http://127.0.0.1:{port}/files/data.xlsx">工资表附件.xlsx</a></h3></div>
</body></html>"""

DETAIL_HTML = """<!DOCTYPE html><html><body><h1>运维信息页</h1>
<p>内网入口 10.12.3.45，值班电话 13912345678，堡垒机地址见内部门户。</p></body></html>"""

RISK_HTML = "<html><body><div>百度安全验证，请完成验证码后继续</div></body></html>"


def _build_xlsx() -> bytes:
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.append(["姓名", "手机号", "内网IP"])
    ws.append(["张三", "13800138000", "192.168.10.20"])
    ws.append(["会议纪要", "", ""])
    import io

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


class FixtureHandler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def _send(self, body: bytes, ctype: str, status: int = 200):
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = self.path
        if path.startswith("/search"):
            self._send(
                SEARCH_HTML.format(port=FIXTURE_PORT).encode("utf-8"), "text/html; charset=utf-8"
            )
        elif path.startswith("/detail/"):
            self._send(DETAIL_HTML.encode("utf-8"), "text/html; charset=utf-8")
        elif path.startswith("/risk"):
            self._send(RISK_HTML.encode("utf-8"), "text/html; charset=utf-8")
        elif path.startswith("/files/data.xlsx"):
            self._send(_build_xlsx(), (
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            ))
        else:
            self._send(b"not found", "text/plain", 404)


def start_fixture():
    server = ThreadingHTTPServer(("127.0.0.1", FIXTURE_PORT), FixtureHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server


def wait_backend():
    for _ in range(60):
        try:
            with socket.create_connection(("127.0.0.1", BACKEND_PORT), timeout=1):
                return
        except OSError:
            time.sleep(0.5)
    raise RuntimeError("后端未在 30s 内启动")


async def wait_status(client, task_id, target, timeout=60):
    deadline = time.time() + timeout
    while time.time() < deadline:
        t = await client.get(f"/api/tasks/{task_id}")
        status = t.json()["status"]
        if status in target:
            return t.json()
        if status == "failed" and "failed" not in target:
            # 失败时仍返回，调用方自行断言
            return t.json()
        await asyncio.sleep(0.5)
    raise AssertionError(f"task {task_id} 未在 {timeout}s 内到达 {target}")


class WsCollector:
    def __init__(self, task_id):
        self.task_id = task_id
        self.events = []
        self.task_done = asyncio.Event()
        self.got_risk = asyncio.Event()
        self._task = None

    async def __aenter__(self):
        self._task = asyncio.create_task(self._run())
        return self

    async def _run(self):
        async with websockets.connect(
            f"ws://127.0.0.1:{BACKEND_PORT}/ws/tasks/{self.task_id}"
        ) as ws:
            async for message in ws:
                evt = json.loads(message)
                self.events.append(evt)
                if evt.get("type") == "risk_alert":
                    self.got_risk.set()
                if evt.get("type") == "task_done":
                    self.task_done.set()
                    return

    async def __aexit__(self, *args):
        self._task.cancel()


async def main():
    fixture = start_fixture()
    # 输出写文件而非 PIPE：Playwright node 驱动继承 stdout，
    # PIPE 缓冲写满后会反向阻塞驱动，导致抓取命令永久挂起
    log_path = ARTIFACT_DIR / "backend.log"
    log_fh = log_path.open("wb")
    backend = subprocess.Popen(
        [VENV_PY, "run.py"],
        cwd=str(Path(__file__).resolve().parents[1]),
        stdout=log_fh,
        stderr=subprocess.STDOUT,
        env={**os.environ, "SDSCAN_PORT": str(BACKEND_PORT)},
    )
    created = {"tasks": [], "platforms": [], "rule": None}
    success = False
    try:
        wait_backend()
        async with httpx.AsyncClient(base_url=BACKEND, timeout=60) as api:
            # ---- 平台：web 通道指向 fixture
            p = await api.post("/api/platforms", json={
                "code": "e2e_web",
                "name": "E2E本地站",
                "channel_type": "web",
                "url_template": f"{FIXTURE}/search?q={{keyword}}&pn={{page}}",
                "page_start": 0,
                "page_step": 10,
                "selectors": {"container": "div.r", "title": "h3 a", "link": "h3 a::attr(href)"},
                "risk_control_hints": {"url_patterns": [], "page_keywords": ["百度安全验证"]},
            })
            assert p.status_code == 201, p.text
            platform_id = p.json()["id"]
            created["platforms"].append(platform_id)

            risk_platform = (await api.post("/api/platforms", json={
                "code": "e2e_risk",
                "name": "E2E风控站",
                "channel_type": "web",
                "url_template": f"{FIXTURE}/risk?q={{keyword}}&pn={{page}}",
                "page_start": 0,
                "page_step": 0,
                "selectors": {"container": "div.r", "title": "h3 a", "link": "h3 a::attr(href)"},
                "risk_control_hints": {"url_patterns": [], "page_keywords": ["百度安全验证"]},
            })).json()
            created["platforms"].append(risk_platform["id"])

            # ---- 平台测试（截图）
            t = await api.post(f"/api/platforms/{platform_id}/test", json={"keyword": "示范单位"})
            body = t.json()
            assert body["count"] >= 3, body
            assert body["screenshot_url"], body
            shot = await api.get(body["screenshot_url"])
            assert shot.status_code == 200 and len(shot.content) > 1000
            print(f"[ok] 平台测试：解析 {body['count']} 条，截图 {len(shot.content)} 字节")

            # ---- 规则正则校验
            bad = await api.post("/api/rules", json={
                "name": "非法正则", "category": "内网信息", "level": "low", "pattern": "([0-9]"
            })
            assert bad.status_code == 400
            print("[ok] 非法正则被拦截")

            # ---- T1 全链路（含 WS 事件）
            task = (await api.post("/api/tasks", json={
                "name": "E2E-T1", "template_type": "T1",
                "keywords": "示范单位", "platform_ids": [platform_id],
                "max_pages": 1, "request_interval": 0.1,
            })).json()
            created["tasks"].append(task["id"])
            ws_col = WsCollector(task["id"])
            await ws_col.__aenter__()
            await api.post(f"/api/tasks/{task['id']}/start")
            done = await wait_status(api, task["id"], {"done"}, timeout=60)
            assert done["status"] == "done", done
            await asyncio.wait_for(ws_col.task_done.wait(), 10)
            results = (await api.get("/api/results", params={"task_id": task["id"]})).json()
            assert results["total"] >= 3, results
            assert any(r["screenshot_path"] for r in results["items"])
            kinds = {e["type"] for e in ws_col.events}
            assert {"unit_status", "result", "stats", "task_done", "log"} <= kinds, kinds
            print(f"[ok] T1：{results['total']} 条结果，WS 事件 {sorted(kinds)}")
            await ws_col.__aexit__()

            # ---- 断点续跑：两页任务，中途取消，再启动
            task2 = (await api.post("/api/tasks", json={
                "name": "E2E-T1-resume", "template_type": "T1",
                "keywords": "示范单位", "platform_ids": [platform_id],
                "max_pages": 2, "request_interval": 0.8,
            })).json()
            created["tasks"].append(task2["id"])
            await api.post(f"/api/tasks/{task2['id']}/start")
            deadline = time.time() + 20
            cancelled = False
            while time.time() < deadline:
                cur = (await api.get(f"/api/tasks/{task2['id']}")).json()
                if (cur.get("stats") or {}).get("done"):
                    await api.post(f"/api/tasks/{task2['id']}/cancel")
                    cancelled = True
                    break
                await asyncio.sleep(0.2)
            assert cancelled, "未捕获到可取消窗口"
            await wait_status(api, task2["id"], {"failed", "done"}, timeout=30)
            # 重新启动（跳过已 done 组合）；等待调度槽释放
            for _ in range(20):
                r = await api.post(f"/api/tasks/{task2['id']}/start")
                if r.status_code == 200:
                    break
                await asyncio.sleep(0.5)
            else:
                raise AssertionError("取消后任务槽未释放，无法重启")
            final = await wait_status(api, task2["id"], {"done"}, timeout=60)
            assert final["status"] == "done", final
            print(f"[ok] 断点续跑：取消后重启完成 {final['stats']}")

            # ---- T5 正文核查 + 页面级命中
            t5 = (await api.post("/api/tasks", json={
                "name": "E2E-T5", "template_type": "T5",
                "unit_name": "示范单位", "domain_scope": "127.0.0.1",
                "platform_ids": [platform_id], "max_pages": 1,
                "request_interval": 0.1,
                "params": {"t5_max_detail": 5},
            })).json()
            created["tasks"].append(t5["id"])
            await api.post(f"/api/tasks/{t5['id']}/start")
            await wait_status(api, t5["id"], {"done"}, timeout=90)
            hits = (await api.get("/api/hits", params={"task_id": t5["id"], "source_type": "page"})).json()
            cats = {h["category"] for h in hits["items"]}
            assert "内网信息" in cats and "联系方式" in cats, cats
            assert all("*" in h["matched_text"] or h["matched_text"] != "10.12.3.45" for h in hits["items"])
            print(f"[ok] T5：页面命中 {hits['total']} 条 {cats}（已脱敏）")

            # ---- T3 附件 + 附件级命中
            t3 = (await api.post("/api/tasks", json={
                "name": "E2E-T3", "template_type": "T3",
                "unit_name": "示范单位", "domain_scope": "127.0.0.1",
                "platform_ids": [platform_id], "max_pages": 1,
                "request_interval": 0.1,
                "params": {"t3_download_limit": 5},
            })).json()
            created["tasks"].append(t3["id"])
            await api.post(f"/api/tasks/{t3['id']}/start")
            await wait_status(api, t3["id"], {"done"}, timeout=90)
            atts = (await api.get("/api/attachments", params={"task_id": t3["id"]})).json()
            assert atts and atts[0]["parse_status"] == "parsed", atts
            dl = await api.get(f"/api/attachments/{atts[0]['id']}/download")
            assert dl.status_code == 200 and len(dl.content) > 100
            ahits = (await api.get("/api/hits", params={"task_id": t3["id"], "source_type": "attachment"})).json()
            assert ahits["total"] >= 1, ahits
            print(f"[ok] T3：附件 {atts[0]['filename']} 解析成功，附件命中 {ahits['total']} 条")

            # ---- T2 域名归集（新链路：仅启用通用搜索兜底源，主域确认后进入闸门）
            t2 = (await api.post("/api/tasks", json={
                "name": "E2E-T2", "template_type": "T2",
                "unit_name": "示范单位",
                "platform_ids": [platform_id], "max_pages": 1,
                "request_interval": 0.1,
                "params": {
                    "apex_providers": ["se_general"],
                    "sub_providers": [],
                    "se_platform_ids": [platform_id],
                    "se_max_pages": 1,
                },
            })).json()
            created["tasks"].append(t2["id"])
            await api.post(f"/api/tasks/{t2['id']}/start")
            gate = await wait_status(api, t2["id"], {"await_gate", "done", "failed"}, timeout=60)
            assert gate["status"] == "await_gate", gate
            domains = (await api.get("/api/domains",
                                     params={"task_id": t2["id"], "layer": "apex"})).json()
            names = {d["domain"] for d in domains}
            assert "demo-unit.gov.cn" in names, names
            print(f"[ok] T2：候选主域 {names}，任务进入 await_gate 闸门")

            # ---- Excel 导出
            export = await api.get("/api/results/export", params={"task_id": t5["id"]})
            assert export.status_code == 200 and len(export.content) > 1000
            print(f"[ok] Excel 导出 {len(export.content)} 字节")

            # ---- 风控检测（取消任务后清理）
            rt = (await api.post("/api/tasks", json={
                "name": "E2E-RISK", "template_type": "T1",
                "keywords": "测试", "platform_ids": [risk_platform["id"]],
                "max_pages": 1, "request_interval": 0.1,
            })).json()
            created["tasks"].append(rt["id"])
            rws = WsCollector(rt["id"])
            await rws.__aenter__()
            await api.post(f"/api/tasks/{rt['id']}/start")
            await asyncio.wait_for(rws.got_risk.wait(), 30)
            units = (await api.get(f"/api/tasks/{rt['id']}/units")).json()
            assert any(u["status"] == "blocked" for u in units), units
            await api.post(f"/api/tasks/{rt['id']}/cancel")
            await wait_status(api, rt["id"], {"failed", "done"}, timeout=30)
            await rws.__aexit__()
            print("[ok] 风控：risk_alert 已推送，组合标记 blocked")

            success = True
            print("\n==== E2E ALL PASSED ====")
    finally:
        # 清理
        try:
            async with httpx.AsyncClient(base_url=BACKEND, timeout=20) as api:
                from sqlalchemy import delete
                sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
                from app.database import SessionLocal
                from app import models

                db = SessionLocal()
                for tid in created["tasks"]:
                    for model in (models.SensitiveHit, models.Attachment,
                                  models.SearchResult, models.DomainList, models.TaskUnit):
                        db.execute(delete(model).where(model.task_id == tid))
                db.commit()
                for tid in created["tasks"]:
                    await api.delete(f"/api/tasks/{tid}")
                for pid in created["platforms"]:
                    await api.delete(f"/api/platforms/{pid}")
                db.close()
        except Exception as exc:
            print("清理失败（不影响结论）：", exc)
        backend.terminate()
        try:
            backend.wait(timeout=10)
        except subprocess.TimeoutExpired:
            backend.kill()
            backend.wait(timeout=10)
        log_fh.close()
        if not success:
            lines = log_path.read_text(encoding="utf-8", errors="ignore").splitlines()
            print("\n---- backend log (tail 30) ----")
            print("\n".join(lines[-30:]))
        fixture.shutdown()


# ------------------------------------------------------------------
# T2 两阶段流水线：进程内 ASGI + 打桩 provider（不打真网、不弹浏览器）
# ------------------------------------------------------------------
class StubApex:
    code = "stubapex"
    display_name = "打桩主域源"

    def is_configured(self, settings):
        return True

    async def run(self, ctx):
        from app.core.discovery.base import ApexResult, Evidence
        yield ApexResult(
            domain="stub-a.com",
            evidence=Evidence(
                provider="stubapex", icp_no="京ICP备888号",
                icp_unit=ctx.unit_name, site_name="示范单位官网",
                ref_url="https://www.stub-a.com",
            ),
        )
        yield ApexResult(
            domain="stub-b.net",
            evidence=Evidence(
                provider="stubapex", site_name="某同名第三方页面",
                ref_url="https://www.stub-b.net/x",
            ),
        )


class StubSub:
    code = "stubsub"
    display_name = "打桩子域源"

    def is_configured(self, settings):
        return True

    async def run(self, ctx, apex):
        from app.core.discovery.base import Evidence, SubResult
        if apex != "stub-a.com":
            return
        for host in ("www.stub-a.com", "vpn.stub-a.com"):
            yield SubResult(
                host=host, apex=apex,
                evidence=Evidence(provider="stubsub", stage="sub",
                                  ref_url=f"https://{host}"),
            )


async def test_t2_pipeline_inprocess():
    """阶段A → 闸门 → 400 分支 → 确认主域 → 阶段B → DNS验活（假解析）→ 导出。"""
    from app.database import init_db
    from app.main import app
    from app.core.discovery import registry
    from app.core.discovery import dns as dns_mod
    from app.ws.manager import manager

    init_db()
    registry.set_override("stubapex", StubApex())
    registry.set_override("stubsub", StubSub())

    async def fake_resolve(host: str, timeout: float = 5.0):
        return ["10.0.0.1"] if host == "www.stub-a.com" else []

    orig_resolve = dns_mod.resolve_host
    dns_mod.resolve_host = fake_resolve

    task_id = None
    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://t2",
                                      timeout=30) as api:
            task = (await api.post("/api/tasks", json={
                "name": "E2E-T2-pipeline", "template_type": "T2",
                "unit_name": "示范单位有限公司", "keywords": "示范单位",
                "request_interval": 0,
                "params": {
                    "apex_providers": ["stubapex"],
                    "sub_providers": ["stubsub"],
                    "engine_max_pages": 1,
                },
            })).json()
            task_id = task["id"]
            r = await api.post(f"/api/tasks/{task_id}/start")
            assert r.status_code == 200, r.text

            gate = await wait_status(api, task_id, {"await_gate"}, timeout=30)
            assert gate["status"] == "await_gate", gate

            apex = (await api.get("/api/domains",
                                   params={"task_id": task_id, "layer": "apex"})).json()
            by_domain = {d["domain"]: d for d in apex}
            assert set(by_domain) == {"stub-a.com", "stub-b.net"}, by_domain
            assert by_domain["stub-a.com"]["confidence"] == "high"
            assert by_domain["stub-b.net"]["confidence"] == "low"
            ev = (await api.get(
                f"/api/domains/{by_domain['stub-a.com']['id']}/evidence")).json()
            assert ev and ev[0]["icp_unit"] == "示范单位有限公司"

            # 未确认主域时枚举 → 400
            bad = await api.post(f"/api/tasks/{task_id}/enumerate-subs")
            assert bad.status_code == 400, bad.text

            # 确认高置信主域，驳回落低置信同名站
            await api.post("/api/domains/batch",
                           json={"ids": [by_domain["stub-a.com"]["id"]],
                                 "status": "confirmed"})
            await api.post("/api/domains/batch",
                           json={"ids": [by_domain["stub-b.net"]["id"]],
                                 "status": "rejected"})

            runs = (await api.get(f"/api/tasks/{task_id}/providers")).json()
            assert any(r["provider"] == "stubapex" and r["status"] == "done" for r in runs)

            # 阶段 B
            r = await api.post(f"/api/tasks/{task_id}/enumerate-subs")
            assert r.status_code == 200, r.text
            final = await wait_status(api, task_id, {"done"}, timeout=30)
            assert final["status"] == "done", final

            subs = (await api.get("/api/domains",
                                   params={"task_id": task_id, "layer": "sub"})).json()
            sub_map = {s["domain"]: s for s in subs}
            assert set(sub_map) == {"www.stub-a.com", "vpn.stub-a.com"}, sub_map
            assert sub_map["www.stub-a.com"]["alive"] is True
            assert sub_map["www.stub-a.com"]["resolved_ip"] == "10.0.0.1"
            assert sub_map["vpn.stub-a.com"]["alive"] is False
            assert all(s["parent_domain"] == "stub-a.com" for s in subs)

            # WS 事件序列（从进程内 manager 缓冲读取）
            kinds = {e["type"] for e in manager._buffers.get(task_id, [])}
            assert {"provider_status", "domain", "domain_evidence",
                    "t2_gate", "task_done"} <= kinds, kinds

            # 导出
            export = await api.get("/api/domains/export/xlsx",
                                    params={"task_id": task_id})
            assert export.status_code == 200 and len(export.content) > 500
            print("[ok] T2 两阶段流水线（打桩）：主域置信度/闸门/子域/验活/导出 全部通过")
    finally:
        dns_mod.resolve_host = orig_resolve
        registry.set_override("stubapex", None)
        registry.set_override("stubsub", None)
        manager.clear(task_id) if task_id else None
        if task_id is not None:
            # 直接清理（进程内无 HTTP 服务时仍可用 ORM）
            from sqlalchemy import delete
            from app.database import SessionLocal
            from app import models
            db = SessionLocal()
            for model in (models.DomainEvidence, models.T2ProviderRun,
                          models.DomainList):
                db.execute(delete(model).where(model.task_id == task_id))
            db.execute(delete(models.Task).where(models.Task.id == task_id))
            db.commit()
            db.close()


async def run_all():
    await main()
    await test_t2_pipeline_inprocess()


if __name__ == "__main__":
    asyncio.run(run_all())
