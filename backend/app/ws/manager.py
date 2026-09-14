"""WebSocket 连接管理：按任务广播事件，并保留最近事件缓冲。

事件类型：unit_status / result / stats / risk_alert / task_done /
domain / attachment / log（终端窗口逐行输出）。
"""
from __future__ import annotations

import asyncio
from collections import defaultdict

from fastapi import WebSocket

BUFFER_LIMIT = 500


class ConnectionManager:
    def __init__(self) -> None:
        self._conns: dict[int, set[WebSocket]] = defaultdict(set)
        self._lock = asyncio.Lock()
        # 任务事件回放缓冲，详情页晚连接也能看到已有进度
        self._buffers: dict[int, list[dict]] = defaultdict(list)

    async def connect(self, task_id: int, ws: WebSocket) -> None:
        await ws.accept()
        async with self._lock:
            self._conns[task_id].add(ws)
            history = list(self._buffers.get(task_id, []))
        for event in history:
            await ws.send_json(event)

    def disconnect(self, task_id: int, ws: WebSocket) -> None:
        self._conns.get(task_id, set()).discard(ws)

    async def broadcast(self, task_id: int, event: dict) -> None:
        """向任务所有连接推送，同时写入缓冲。"""
        async with self._lock:
            buf = self._buffers[task_id]
            buf.append(event)
            if len(buf) > BUFFER_LIMIT:
                del buf[: len(buf) - BUFFER_LIMIT]
            conns = list(self._conns.get(task_id, set()))

        dead = []
        for ws in conns:
            try:
                await ws.send_json(event)
            except Exception:
                dead.append(ws)
        if dead:
            async with self._lock:
                for ws in dead:
                    self._conns[task_id].discard(ws)

    def clear(self, task_id: int) -> None:
        self._buffers.pop(task_id, None)


manager = ConnectionManager()
