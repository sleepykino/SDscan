"""任务级 WebSocket：/ws/tasks/{task_id}。"""
from __future__ import annotations

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from ..database import SessionLocal
from ..models import Task
from ..ws.manager import manager

router = APIRouter()


@router.websocket("/ws/tasks/{task_id}")
async def task_ws(ws: WebSocket, task_id: int) -> None:
    db = SessionLocal()
    try:
        task = db.get(Task, task_id)
        if task is None:
            await ws.close(code=1008)
            return
    finally:
        db.close()

    await manager.connect(task_id, ws)
    try:
        while True:
            # 客户端暂不下发指令，仅维持连接（读心跳/占位）
            await ws.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(task_id, ws)
    except Exception:
        manager.disconnect(task_id, ws)
