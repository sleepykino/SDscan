"""任务 CRUD、生命周期控制、组合进度与人工过码。"""
from __future__ import annotations

from datetime import datetime
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ..config import DATA_DIR, load_settings
from ..core.engine.web_collector import web_collector
from ..core.scheduler import scheduler
from ..database import get_db
from ..models import (
    Attachment,
    DomainList,
    Platform,
    SensitiveHit,
    SearchResult,
    Task,
    TaskUnit,
)
from ..ws.manager import manager
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
    # 手动级联删除（SearchResult/Hits/Attachment/DomainList 未配置 ORM cascade）
    db.execute(delete(SensitiveHit).where(SensitiveHit.task_id == task_id))
    for att in db.execute(
        select(Attachment).where(Attachment.task_id == task_id)
    ).scalars():
        if att.file_path:
            file = DATA_DIR / att.file_path
            try:
                if file.is_file():
                    file.unlink()
            except OSError:
                pass
        db.delete(att)
    db.execute(delete(SearchResult).where(SearchResult.task_id == task_id))
    db.execute(delete(DomainList).where(DomainList.task_id == task_id))
    db.execute(delete(TaskUnit).where(TaskUnit.task_id == task_id))
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
async def cancel_task(task_id: int, db: Session = Depends(get_db)):
    task = db.get(Task, task_id)
    if task is None:
        raise HTTPException(404, "任务不存在")
    has_runner = await scheduler.cancel(task_id)
    if not has_runner:
        # 无运行实例（典型：服务重启遗留的 running 状态）——直接落库为已取消
        if task.status not in ("running", "paused_manual"):
            raise HTTPException(400, f"任务状态 {task.status}，无需取消")
        task.status = "failed"
        task.error_msg = "用户取消"
        task.finished_at = datetime.now()
        db.commit()
        await manager.broadcast(
            task_id,
            {"type": "task_done", "status": "failed", "error": "用户取消"},
        )
        return {"message": "已取消"}
    return {"message": "取消中"}


# ---------------------------------------------------------------- 人工过码
@router.post("/{task_id}/risk/{platform_id}/solve-start", response_model=schemas.MessageOut)
async def solve_start(task_id: int, platform_id: int, db: Session = Depends(get_db)):
    platform = db.get(Platform, platform_id)
    if platform is None:
        raise HTTPException(404, "平台不存在")
    url = web_collector.last_blocked_url.get(platform_id)
    if not url:
        # 回退：站点首页（搜索模板的空关键词页或 AJAX 接口不适合人工过码）
        parsed = urlparse(platform.url_template)
        url = f"{parsed.scheme}://{parsed.netloc}/" if parsed.netloc else platform.url_template
    try:
        await web_collector.start_solve(url, extra_headers=dict(platform.headers or {}))
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
