from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from ..config import get_settings
from ..database import get_session_factory
from ..models import Task
from ..security import decode_token

router = APIRouter(tags=["WebSocket"])


@router.websocket("/ws/task/{task_id}")
async def task_progress(websocket: WebSocket, task_id: str) -> None:
    settings = get_settings()
    if not settings.disable_auth:
        token = websocket.query_params.get("token", "")
        try:
            decode_token(token)
        except Exception:
            await websocket.close(code=4401)
            return
    await websocket.accept()
    factory = get_session_factory()
    last_progress = -1
    try:
        while True:
            with factory() as db:
                task = db.get(Task, task_id)
            if task is None:
                await websocket.send_json({"error": "task not found"})
                await websocket.close(code=4404)
                return
            payload = {
                "task_id": task_id,
                "progress": task.progress,
                "message": task.message,
                "status": task.status,
                "stage": task.current_stage,
                "estimated_time_remaining": max(0, round((100 - task.progress) / 10)),
            }
            if task.progress != last_progress or task.status in {"completed", "failed"}:
                await websocket.send_text(json.dumps(payload, ensure_ascii=False))
                last_progress = task.progress
            if task.status in {"completed", "failed"}:
                await websocket.close(code=1000)
                return
            await asyncio.sleep(1)
    except WebSocketDisconnect:
        return
