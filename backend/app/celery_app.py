from __future__ import annotations

import logging

from celery import Celery

from .config import get_settings

logger = logging.getLogger(__name__)

settings = get_settings()

celery = Celery("bid_agent", broker=settings.redis_url, backend=settings.redis_url)
celery.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="Asia/Shanghai",
    enable_utc=True,
    task_track_started=True,
)


@celery.task(name="bid_agent.run_pipeline_task")
def run_pipeline_task(
    task_id: str,
    stages: list[str] | None = None,
    mode: str = "fast",
    industry: str = "auto",
    use_kb: bool = True,
    with_check: bool = True,
) -> dict:
    from .pipeline import PipelineRunner

    runner = PipelineRunner()
    return runner.run(task_id=task_id, stages=stages, mode=mode, industry=industry, use_kb=use_kb, with_check=with_check)
