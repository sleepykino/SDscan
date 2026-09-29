"""T2 域名清单：查询、证据、人工甄别（单条/批量）与导出。"""
from __future__ import annotations

import io

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from openpyxl import Workbook

from ..database import get_db
from ..models import DomainEvidence, DomainList
from .. import schemas

router = APIRouter(prefix="/domains", tags=["domains"])


def _filtered_stmt(*, task_id, status, unit_name, layer, confidence,
                   parent_domain, alive) -> select:
    stmt = select(DomainList).order_by(DomainList.id.desc())
    if task_id is not None:
        stmt = stmt.where(DomainList.task_id == task_id)
    if status:
        stmt = stmt.where(DomainList.status == status)
    if unit_name:
        stmt = stmt.where(DomainList.unit_name.contains(unit_name))
    if layer:
        stmt = stmt.where(DomainList.layer == layer)
    if confidence:
        stmt = stmt.where(DomainList.confidence == confidence)
    if parent_domain:
        stmt = stmt.where(DomainList.parent_domain == parent_domain)
    if alive is not None:
        stmt = stmt.where(DomainList.alive.is_(alive))
    return stmt


def _serialize(db: Session, rows: list[DomainList]) -> list[schemas.DomainOut]:
    counts = dict(
        db.execute(
            select(DomainEvidence.domain_list_id, func.count(DomainEvidence.id))
            .where(DomainEvidence.domain_list_id.in_([r.id for r in rows] or [0]))
            .group_by(DomainEvidence.domain_list_id)
        ).all()
    ) if rows else {}
    result = []
    for row in rows:
        out = schemas.DomainOut.model_validate(row)
        out.evidence_count = counts.get(row.id, 0)
        result.append(out)
    return result


@router.get("", response_model=list[schemas.DomainOut])
def list_domains(
    task_id: int | None = None,
    status: str | None = None,
    unit_name: str | None = None,
    layer: str | None = None,
    confidence: str | None = None,
    parent_domain: str | None = None,
    alive: bool | None = None,
    db: Session = Depends(get_db),
):
    rows = list(db.execute(_filtered_stmt(
        task_id=task_id, status=status, unit_name=unit_name, layer=layer,
        confidence=confidence, parent_domain=parent_domain, alive=alive,
    )).scalars())
    return _serialize(db, rows)


@router.get("/{domain_id}/evidence", response_model=list[schemas.EvidenceOut])
def list_evidence(domain_id: int, db: Session = Depends(get_db)):
    if db.get(DomainList, domain_id) is None:
        raise HTTPException(404, "域名不存在")
    return list(db.execute(
        select(DomainEvidence)
        .where(DomainEvidence.domain_list_id == domain_id)
        .order_by(DomainEvidence.id)
    ).scalars())


@router.patch("/{domain_id}", response_model=schemas.DomainOut)
def patch_domain(
    domain_id: int,
    payload: schemas.DomainPatch,
    db: Session = Depends(get_db),
):
    row = db.get(DomainList, domain_id)
    if row is None:
        raise HTTPException(404, "域名不存在")
    _apply_status(db, row, payload.status, cascade=False)
    db.commit()
    return _serialize(db, [row])[0]


@router.post("/batch", response_model=list[schemas.DomainOut])
def batch_status(payload: schemas.BatchStatusIn, db: Session = Depends(get_db)):
    if not payload.ids:
        return []
    rows = list(db.execute(
        select(DomainList).where(DomainList.id.in_(payload.ids))
    ).scalars())
    for row in rows:
        _apply_status(db, row, payload.status, cascade=payload.cascade)
    db.commit()
    return _serialize(db, rows)


def _apply_status(db: Session, row: DomainList, status: str, *, cascade: bool) -> None:
    row.status = status
    # 驳回主域且 cascade：级联驳回其下子域；确认不自动恢复人工状态
    if cascade and row.layer == "apex" and status == "rejected":
        for sub in db.execute(
            select(DomainList).where(
                DomainList.task_id == row.task_id,
                DomainList.layer == "sub",
                DomainList.parent_domain == row.domain,
                DomainList.status != "rejected",
            )
        ).scalars():
            sub.status = "rejected"


@router.get("/export/xlsx")
def export_domains(
    task_id: int | None = None,
    status: str | None = None,
    layer: str | None = None,
    confidence: str | None = None,
    parent_domain: str | None = None,
    alive: bool | None = None,
    db: Session = Depends(get_db),
):
    rows = list(db.execute(_filtered_stmt(
        task_id=task_id, status=status, unit_name=None, layer=layer,
        confidence=confidence, parent_domain=parent_domain, alive=alive,
    )).scalars())

    wb = Workbook()
    ws = wb.active
    ws.title = "域名清单"
    ws.append(["任务ID", "单位", "层级", "域名", "父主域", "置信度", "状态",
               "存活", "解析IP", "主来源", "证据数", "证据摘要"])
    for row in rows:
        evs = list(db.execute(
            select(DomainEvidence)
            .where(DomainEvidence.domain_list_id == row.id)
            .order_by(DomainEvidence.id)
        ).scalars())
        summary = "；".join(
            f"{e.provider}:" + "/".join(
                x for x in (e.icp_no, e.site_name, e.cert_org) if x
            )
            for e in evs[:5]
        )
        ws.append([
            row.task_id, row.unit_name,
            "主域" if row.layer == "apex" else "子域",
            row.domain, row.parent_domain, row.confidence, row.status,
            {True: "存活", False: "不存活"}.get(row.alive, "-"),
            row.resolved_ip, row.provider, len(evs), summary,
        ])
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    headers = {"Content-Disposition": "attachment; filename=domains.xlsx"}
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers=headers,
    )
