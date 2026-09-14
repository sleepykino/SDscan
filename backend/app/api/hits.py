"""敏感命中列表。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import SensitiveHit, SensitiveRule
from .. import schemas

router = APIRouter(prefix="/hits", tags=["hits"])


@router.get("")
def list_hits(
    level: str | None = None,
    category: str | None = None,
    source_type: str | None = None,
    task_id: int | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    db: Session = Depends(get_db),
):
    stmt = select(SensitiveHit).order_by(SensitiveHit.id.desc())
    if level:
        stmt = stmt.where(SensitiveHit.level == level)
    if category:
        stmt = stmt.where(SensitiveHit.category == category)
    if source_type:
        stmt = stmt.where(SensitiveHit.source_type == source_type)
    if task_id is not None:
        stmt = stmt.where(SensitiveHit.task_id == task_id)

    all_rows = list(db.execute(stmt).scalars())
    total = len(all_rows)
    rows = all_rows[(page - 1) * page_size : page * page_size]

    rule_names = {
        r.id: r.name
        for r in db.execute(select(SensitiveRule)).scalars()
    }
    items = [
        {
            **schemas.HitOut.model_validate(hit).model_dump(),
            "rule_name": rule_names.get(hit.rule_id, ""),
        }
        for hit in rows
    ]
    return {"total": total, "items": items}
