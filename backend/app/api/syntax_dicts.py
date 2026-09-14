"""语法包装字典 CRUD。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import SyntaxDict
from .. import schemas

router = APIRouter(prefix="/syntax-dicts", tags=["syntax-dicts"])


@router.get("", response_model=list[schemas.SyntaxOut])
def list_syntax(
    template_type: str | None = None,
    enabled: bool | None = None,
    db: Session = Depends(get_db),
):
    stmt = select(SyntaxDict).order_by(SyntaxDict.id)
    if template_type:
        stmt = stmt.where(SyntaxDict.template_type == template_type)
    if enabled is not None:
        stmt = stmt.where(SyntaxDict.enabled.is_(enabled))
    return list(db.execute(stmt).scalars())


@router.post("", response_model=schemas.SyntaxOut, status_code=201)
def create_syntax(payload: schemas.SyntaxCreate, db: Session = Depends(get_db)):
    row = SyntaxDict(**payload.model_dump())
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@router.put("/{dict_id}", response_model=schemas.SyntaxOut)
def update_syntax(
    dict_id: int, payload: schemas.SyntaxUpdate, db: Session = Depends(get_db)
):
    row = db.get(SyntaxDict, dict_id)
    if row is None:
        raise HTTPException(404, "语法不存在")
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(row, key, value)
    db.commit()
    db.refresh(row)
    return row


@router.patch("/{dict_id}/toggle", response_model=schemas.SyntaxOut)
def toggle_syntax(dict_id: int, db: Session = Depends(get_db)):
    row = db.get(SyntaxDict, dict_id)
    if row is None:
        raise HTTPException(404, "语法不存在")
    row.enabled = not row.enabled
    db.commit()
    db.refresh(row)
    return row


@router.delete("/{dict_id}", response_model=schemas.MessageOut)
def delete_syntax(dict_id: int, db: Session = Depends(get_db)):
    row = db.get(SyntaxDict, dict_id)
    if row is None:
        raise HTTPException(404, "语法不存在")
    db.delete(row)
    db.commit()
    return {"message": "已删除"}
