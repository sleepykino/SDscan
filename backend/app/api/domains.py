"""T2 域名清单：查询与人工甄别（确认/驳回候选域名）。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import DomainList
from .. import schemas

router = APIRouter(prefix="/domains", tags=["domains"])


@router.get("", response_model=list[schemas.DomainOut])
def list_domains(
    task_id: int | None = None,
    status: str | None = None,
    unit_name: str | None = None,
    db: Session = Depends(get_db),
):
    stmt = select(DomainList).order_by(DomainList.id.desc())
    if task_id is not None:
        stmt = stmt.where(DomainList.task_id == task_id)
    if status:
        stmt = stmt.where(DomainList.status == status)
    if unit_name:
        stmt = stmt.where(DomainList.unit_name.contains(unit_name))
    return list(db.execute(stmt).scalars())


@router.patch("/{domain_id}", response_model=schemas.DomainOut)
def patch_domain(
    domain_id: int,
    payload: schemas.DomainPatch,
    db: Session = Depends(get_db),
):
    row = db.get(DomainList, domain_id)
    if row is None:
        raise HTTPException(404, "域名不存在")
    row.status = payload.status
    db.commit()
    db.refresh(row)
    return row
