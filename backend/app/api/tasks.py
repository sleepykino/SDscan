"""任务 CRUD、生命周期控制、组合进度与人工过码。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import load_settings
from ..core.engine.web_collector import web_collector
from ..core.rule_engine import build_url
from ..core.scheduler import scheduler
from ..database import get_db
from ..models import Task, TaskUnit
from .. import schemas

router = APIRouter(prefix="/tasks", tags=["tasks"])


@router.get("", response_model=list[schemas.TaskOut])
def list_tasks(
    status: str | None = None,
    template_type: str | None = None,
    db: Session = Depends(get_db),
):
    stmt = select(Task).order_by(Task.id.desc())
    if status:
        stmt = stmt.where(Task.status == status)
    if template_type:
        stmt = stmt.where(Task.template_type == template_type)
    return list(db.execute(stmt).scalars())


@router.post("", response_model=schemas.TaskOut, status_code=201)
def create_task(payload: schemas.TaskCreate, db: Session = Depends(get_db)):
    settings = load_settings()
    data = payload.model_dump()
    data.setdefault("request_interval", settings.get("default_request_interval", 5.0))
    task = Task(**data, status="pending", stats={})
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


@router.get("/{task_id}", response_model=schemas.TaskOut)
def get_task(task_id: int, db: Session = Depends(get_db)):
    task = db.get(Task, task_id)
    if task is None:
        raise HTTPException(404, "任务不存在")
    return task


@router.put("/{task_id}", response_model=schemas.TaskOut)
def update_task(
    task_id: int, payload: schemas.TaskUpdate, db: Session = Depends(get_db)
):
    task = db.get(Task, task_id)
    if task is None:
        raise HTTPException(404, "任务不存在")
    if task.status not in ("pending", "failed"):
        raise HTTPException(400, "仅待执行/失败任务可编辑")
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(task, key, value)
    db.commit()
    db.refresh(task)
    return task


@router.delete("/{task_id}", response_model=schemas.MessageOut)
def delete_task(task_id: int, db: Session = Depends(get_db)):
    task = db.get(Task, task_id)
    if task is None:
        raise HTTPException(404, "任务不存在")
    if task_id in scheduler.runs:
        raise HTTPException(400, "任务执行中，请先取消再删除")
    db.delete(task)
    db.commit()
    return {"message": "已删除"}


@router.get("/{task_id}/units", response_model=list[schemas.UnitOut])
def list_units(task_id: int, db: Session = Depends(get_db)):
    return list(
        db.execute(
            select(TaskUnit)
            .where(TaskUnit.task_id == task_id)
            .order_by(TaskUnit.id)
        ).scalars()
    )


@router.post("/{task_id}/start", response_model=schemas.MessageOut)
async def start_task(task_id: int):
    try:
        await scheduler.start(task_id)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    except RuntimeError as exc:
        raise HTTPException(409, str(exc))
    return {"message": "已启动"}


@router.post("/{task_id}/pause", response_model=schemas.MessageOut)
async def pause_task(task_id: int):
    await scheduler.pause(task_id)
    from ..database import SessionLocal

    db = SessionLocal()
    try:
        task = db.get(Task, task_id)
        if task and task.status == "running":
            task.status = "paused_manual"
            db.commit()
    finally:
        db.close()
    return {"message": "已暂停"}


@router.post("/{task_id}/resume", response_model=schemas.MessageOut)
async def resume_task(task_id: int):
    await scheduler.resume(task_id)
    from ..database import SessionLocal

    db = SessionLocal()
    try:
        task = db.get(Task, task_id)
        if task and task.status == "paused_manual":
            task.status = "running"
            db.commit()
    finally:
        db.close()
    return {"message": "已恢复"}


@router.post("/{task_id}/cancel", response_model=schemas.MessageOut)
async def cancel_task(task_id: int):
    await scheduler.cancel(task_id)
    return {"message": "取消中"}


# ---------------------------------------------------------------- 人工过码
@router.post("/{task_id}/risk/{platform_id}/solve-start", response_model=schemas.MessageOut)
async def solve_start(task_id: int, platform_id: int, db: Session = Depends(get_db)):
    platform = db.get(Platform, platform_id)
    if platform is None:
        raise HTTPException(404, "平台不存在")
    url = web_collector.last_blocked_url.get(platform_id)
    if not url:
        # 回退：用平台首页模板
        url = build_url(platform.url_template, "", platform.page_start)
    try:
        await web_collector.start_solve(url)
    except RuntimeError as exc:
        raise HTTPException(409, str(exc))
    except Exception as exc:
        raise HTTPException(500, f"无法打开过码浏览器：{exc}")
    return {"message": "过码窗口已打开"}


@router.post("/{task_id}/risk/{platform_id}/solve-done", response_model=schemas.MessageOut)
async def solve_done(task_id: int, platform_id: int, db: Session = Depends(get_db)):
    platform = db.get(Platform, platform_id)
    if platform is None:
        raise HTTPException(404, "平台不存在")
    try:
        raw_cookie = await web_collector.finish_solve()
    except RuntimeError as exc:
        raise HTTPException(400, str(exc))
    platform.cookie = raw_cookie
    db.commit()
    await scheduler.unblock_platform(task_id, platform_id)
    return {"message": "Cookie 已回填，平台恢复采集"}


@router.post("/{task_id}/risk/{platform_id}/solve-cancel", response_model=schemas.MessageOut)
async def solve_cancel(task_id: int, platform_id: int):
    await web_collector.cancel_solve()
    return {"message": "已取消过码"}
