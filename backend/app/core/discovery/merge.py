"""域名归一化、证据写入与置信度重算（P5 §5/§6）。

所有写库都在 pipeline 的 DB 会话内完成；provider 自身不触库。
"""
from __future__ import annotations

import re
import uuid

from sqlalchemy import select

from ...models import DomainEvidence, DomainList, Task
from ..rule_engine import registrable_domain
from .base import PROVIDER_PRIORITY, STAGE_APEX, Evidence

# 备案/许可证号：京ICP备12345678号 / 京ICP证030173号-1 等
ICP_NO_RE = re.compile(
    r"[京津沪渝冀豫云辽黑湘皖鲁新苏浙赣鄂桂甘晋蒙陕吉闽贵粤青藏川宁琼使领][A-Z0-9]?"
    r"ICP\s*(?:备|证)\s*\d+(?:号)?(?:-\d+)?"
)


def normalize_name(name: str) -> str:
    """单位名归一：去空白、全角括号转半角，用于备案主体精确比对。"""
    if not name:
        return ""
    table = str.maketrans({"（": "(", "）": ")", "\u3000": " ", "　": " "})
    return re.sub(r"\s+", "", name.translate(table)).strip().lower()


def normalize_domain(value: str) -> str:
    """主机/URL → 小写注册主域；无法判定返回空串。"""
    return registrable_domain(value or "")


def normalize_sub_host(host: str) -> str:
    """子域主机名归一：小写、去端口/路径/通配前缀。"""
    host = (host or "").strip().lower()
    host = host.split("://")[-1].split("/")[0].split(":")[0]
    host = host.lstrip("*.").strip(".")
    return host


def gen_wildcard_prefix() -> str:
    return f"sdscan-{uuid.uuid4().hex[:12]}"


def _evidence_matches_name(ev: DomainEvidence, full_norm: str,
                           alias_norm: list[str]) -> bool:
    targets = {full_norm, *alias_norm} - {""}
    cert = normalize_name(ev.cert_org)
    site = normalize_name(ev.site_name)
    for t in targets:
        if cert and (t in cert or cert in t):
            return True
        if site and (t in site or t and t in site):
            return True
    return False


def recompute_confidence(row: DomainList, full_name: str,
                         aliases: list[str]) -> None:
    """根据全部证据重算置信度与主贡献来源（P5 §6）。"""
    full_norm = normalize_name(full_name)
    alias_norm = [normalize_name(a) for a in aliases]
    providers = {e.provider for e in row.evidences}
    level = "low"
    best_provider = ""

    for ev in row.evidences:
        if ev.icp_unit and normalize_name(ev.icp_unit) == full_norm and full_norm:
            level = "high"
            break

    if level != "high":
        cert_hit = any(
            e.cert_org and _evidence_matches_name(e, full_norm, alias_norm)
            for e in row.evidences
        )
        cross_hit = len(providers) >= 2 and any(
            e.site_name and _evidence_matches_name(e, full_norm, alias_norm)
            for e in row.evidences
        )
        if cert_hit or cross_hit:
            level = "medium"

    # 主来源：按优先级取最权威 provider
    ranked = sorted(providers, key=lambda p: PROVIDER_PRIORITY.get(p, 90))
    best_provider = ranked[0] if ranked else row.provider

    row.confidence = level
    if best_provider:
        row.provider = best_provider


def add_evidence(db, row: DomainList, ev: Evidence) -> DomainEvidence | None:
    """追加证据；同 (域名, provider, ref_url) 已存在则返回 None（幂等）。

    先查后插，避免 IntegrityError 回滚冲掉同事务内其他待提交对象。
    """
    ref_url = ev.ref_url[:2000]
    exists = db.execute(
        select(DomainEvidence.id).where(
            DomainEvidence.domain_list_id == row.id,
            DomainEvidence.provider == ev.provider,
            DomainEvidence.ref_url == ref_url,
        )
    ).first()
    if exists:
        return None
    record = DomainEvidence(
        task_id=row.task_id,
        domain_list_id=row.id,
        provider=ev.provider,
        stage=ev.stage,
        icp_no=ev.icp_no[:128],
        icp_unit=ev.icp_unit[:255],
        site_name=ev.site_name[:255],
        cert_org=ev.cert_org[:255],
        ref_url=ref_url,
        detail=ev.detail or {},
    )
    db.add(record)
    db.flush()
    return record


def upsert_apex(db, task: Task, domain: str, ev: Evidence,
                aliases: list[str]) -> tuple[DomainList, DomainEvidence | None, bool]:
    """阶段 A 归并。返回 (行, 新证据或None, 是否新域名)。"""
    domain = normalize_domain(domain)
    row = db.execute(
        select(DomainList).where(
            DomainList.task_id == task.id, DomainList.domain == domain
        )
    ).scalar_one_or_none()
    is_new = row is None
    if row is None:
        row = DomainList(
            task_id=task.id, unit_name=task.unit_name, domain=domain,
            source="", status="candidate", layer=STAGE_APEX,
        )
        db.add(row)
        db.flush()
    if not row.source:
        row.source = f"{ev.provider}"
    record = add_evidence(db, row, ev)
    recompute_confidence(row, task.unit_name, aliases)
    return row, record, is_new


def upsert_sub(db, task: Task, host: str, apex: str,
               ev: Evidence | None) -> tuple[DomainList, DomainEvidence | None, bool]:
    """阶段 B 归并。host 必须落在 apex 之下。"""
    host = normalize_sub_host(host)
    if not host or (host != apex and not host.endswith("." + apex)):
        raise ValueError(f"子域 {host} 不属于主域 {apex}")
    row = db.execute(
        select(DomainList).where(
            DomainList.task_id == task.id, DomainList.domain == host
        )
    ).scalar_one_or_none()
    is_new = row is None
    if row is None:
        row = DomainList(
            task_id=task.id, unit_name=task.unit_name, domain=host,
            source="", status="candidate", layer="sub", parent_domain=apex,
        )
        db.add(row)
        db.flush()
    elif not row.parent_domain:
        row.parent_domain = apex
        row.layer = "sub"
    record = add_evidence(db, row, ev) if ev else None
    if record is not None:
        recompute_confidence(row, task.unit_name, [])
    elif not row.provider:
        row.provider = ev.provider if ev else ""
    return row, record, is_new
