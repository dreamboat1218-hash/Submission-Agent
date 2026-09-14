"""任务进度发布中心。

内存字典保证单进程开发模式可用；Celery 模式下 WebSocket 直接轮询数据库，
因此本模块只作为最近一条进度消息的补充缓存。
"""
from __future__ import annotations

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)


class ProgressHub:
    def __init__(self) -> None:
        self._events: dict[str, dict[str, Any]] = {}

    def publish(self, task_id: str, event: dict[str, Any]) -> None:
        self._events[task_id] = event
        try:
            import redis
            from .config import get_settings

            client = redis.from_url(get_settings().redis_url, socket_connect_timeout=0.3)
            client.publish("bid_task_events", json.dumps({"task_id": task_id, **event}, ensure_ascii=False))
        except Exception:  # Redis 不可用时静默降级
            pass

    def latest(self, task_id: str) -> dict[str, Any] | None:
        return self._events.get(task_id)


hub = ProgressHub()
