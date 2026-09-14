"""敏感规则 CRUD + 启停 + 正则校验。"""
from __future__ import annotations

import re

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import SensitiveRule
from .. import schemas

router = APIRouter(prefix="/rules", tags=["rules"])


def _validate_pattern(pattern: str) -> None:
    try:
        re.compile(pattern)
    except re.error as exc:
        raise HTTPException(400, f"非法正则：{exc}")


@router.get("", response_model=list[schemas.RuleOut])
def list_rules(
    enabled: bool | None = None,
    level: str | None = None,
    category: str | None = None,
    db: Session = Depends(get_db),
):
    stmt = select(SensitiveRule).order_by(SensitiveRule.id)
    if enabled is not None:
        stmt = stmt.where(SensitiveRule.enabled.is_(enabled))
    if level:
        stmt = stmt.where(SensitiveRule.level == level)
    if category:
        stmt = stmt.where(SensitiveRule.category == category)
    return list(db.execute(stmt).scalars())


@router.post("", response_model=schemas.RuleOut, status_code=201)
def create_rule(payload: schemas.RuleCreate, db: Session = Depends(get_db)):
    _validate_pattern(payload.pattern)
    rule = SensitiveRule(**payload.model_dump())
    db.add(rule)
    db.commit()
    db.refresh(rule)
    return rule


@router.put("/{rule_id}", response_model=schemas.RuleOut)
def update_rule(
    rule_id: int, payload: schemas.RuleUpdate, db: Session = Depends(get_db)
):
    rule = db.get(SensitiveRule, rule_id)
    if rule is None:
        raise HTTPException(404, "规则不存在")
    data = payload.model_dump(exclude_unset=True)
    if "pattern" in data:
        _validate_pattern(data["pattern"])
    for key, value in data.items():
        setattr(rule, key, value)
    db.commit()
    db.refresh(rule)
    return rule


@router.patch("/{rule_id}/toggle", response_model=schemas.RuleOut)
def toggle_rule(rule_id: int, db: Session = Depends(get_db)):
    rule = db.get(SensitiveRule, rule_id)
    if rule is None:
        raise HTTPException(404, "规则不存在")
    rule.enabled = not rule.enabled
    db.commit()
    db.refresh(rule)
    return rule


@router.delete("/{rule_id}", response_model=schemas.MessageOut)
def delete_rule(rule_id: int, db: Session = Depends(get_db)):
    rule = db.get(SensitiveRule, rule_id)
    if rule is None:
        raise HTTPException(404, "规则不存在")
    db.delete(rule)
    db.commit()
    return {"message": "已删除"}
