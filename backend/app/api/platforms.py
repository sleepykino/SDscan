"""平台规则 CRUD、启停、选择器测试。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import load_settings
from ..database import get_db
from ..models import Platform
from ..core.engine.api_collector import ApiCollector
from ..core.engine.risk import detect_risk
from ..core.engine.web_collector import web_collector
from ..core.rule_engine import build_url, extract_items, page_offset
from .. import schemas

router = APIRouter(prefix="/platforms", tags=["platforms"])

_api_collector = ApiCollector()


@router.get("", response_model=list[schemas.PlatformOut])
def list_platforms(
    enabled: bool | None = None,
    q: str | None = None,
    db: Session = Depends(get_db),
):
    stmt = select(Platform).order_by(Platform.id)
    if enabled is not None:
        stmt = stmt.where(Platform.enabled.is_(enabled))
    if q:
        like = f"%{q}%"
        stmt = stmt.where(Platform.name.like(like) | Platform.code.like(like))
    return list(db.execute(stmt).scalars())


@router.post("", response_model=schemas.PlatformOut, status_code=201)
def create_platform(payload: schemas.PlatformCreate, db: Session = Depends(get_db)):
    if db.execute(select(Platform).where(Platform.code == payload.code)).scalar_one_or_none():
        raise HTTPException(409, f"code {payload.code} 已存在")
    platform = Platform(**payload.model_dump())
    db.add(platform)
    db.commit()
    db.refresh(platform)
    return platform


@router.get("/{platform_id}", response_model=schemas.PlatformOut)
def get_platform(platform_id: int, db: Session = Depends(get_db)):
    platform = db.get(Platform, platform_id)
    if platform is None:
        raise HTTPException(404, "平台不存在")
    return platform


@router.put("/{platform_id}", response_model=schemas.PlatformOut)
def update_platform(
    platform_id: int,
    payload: schemas.PlatformUpdate,
    db: Session = Depends(get_db),
):
    platform = db.get(Platform, platform_id)
    if platform is None:
        raise HTTPException(404, "平台不存在")
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(platform, key, value)
    db.commit()
    db.refresh(platform)
    return platform


@router.delete("/{platform_id}", response_model=schemas.MessageOut)
def delete_platform(platform_id: int, db: Session = Depends(get_db)):
    platform = db.get(Platform, platform_id)
    if platform is None:
        raise HTTPException(404, "平台不存在")
    db.delete(platform)
    db.commit()
    return {"message": "已删除"}


@router.patch("/{platform_id}/toggle", response_model=schemas.PlatformOut)
def toggle_platform(platform_id: int, db: Session = Depends(get_db)):
    platform = db.get(Platform, platform_id)
    if platform is None:
        raise HTTPException(404, "平台不存在")
    platform.enabled = not platform.enabled
    db.commit()
    db.refresh(platform)
    return platform


@router.post("/{platform_id}/test")
async def test_platform(
    platform_id: int,
    payload: schemas.PlatformTestIn,
    db: Session = Depends(get_db),
):
    """取一个关键词跑 1 页，返回解析条数、截图预览与风控判定，用于调试选择器。"""
    platform = db.get(Platform, platform_id)
    if platform is None:
        raise HTTPException(404, "平台不存在")

    settings = load_settings()
    page_value = page_offset(platform, 1)
    if page_value is None:
        page_value = platform.page_start
    url = build_url(platform.url_template, payload.keyword, page_value)

    if platform.channel_type == "api":
        headers = dict(platform.headers or {})
        token = settings.get("github_token", "")
        if token and platform.code.startswith("github"):
            headers.setdefault("Authorization", f"Bearer {token}")
        page_obj = await _api_collector.fetch(
            url, headers=headers, cookie=platform.cookie or ""
        )
    else:
        page_obj = await web_collector.fetch(
            url,
            cookie=platform.cookie or "",
            extra_headers=dict(platform.headers or {}),
            save_screenshot=payload.save_screenshot,
        )

    risk_reason = None if page_obj.error else detect_risk(
        page_obj, platform.risk_control_hints or {}
    )
    items = [] if page_obj.error else extract_items(page_obj, platform)

    return {
        "request_url": url,
        "final_url": page_obj.url,
        "status": page_obj.status,
        "error": page_obj.error,
        "risk": risk_reason,
        "count": len(items),
        "items": items[:30],
        "screenshot_url": f"/screenshots/{page_obj.screenshot_path}"
        if page_obj.screenshot_path
        else "",
    }
