from __future__ import annotations

import logging
import json
import traceback
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from sqlalchemy.orm import Session

from .config import get_settings
from .database import get_session_factory
from .models import Task
from .modules import compliance, extractor, generator, package_parser, preprocess
from .modules.industry import detect_industry
from .progress import hub

logger = logging.getLogger(__name__)

STAGES = ["preprocess", "extract", "generate", "check"]

ProgressCallback = Callable[[float, str], None]


def _now() -> datetime:
    return datetime.now(timezone.utc)


class PipelineRunner:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.factory = get_session_factory()

    def _session(self) -> Session:
        return self.factory()

    def _publish(self, db: Session, task: Task, progress: float, message: str, status: str | None = None) -> None:
        task.progress = progress
        task.message = message
        if status is not None:
            task.status = status
        db.commit()
        hub.publish(task.id, {"progress": progress, "message": message, "status": task.status, "stage": task.current_stage})

    def run(
        self,
        task_id: str,
        stages: list[str] | None = None,
        mode: str = "fast",
        industry: str = "auto",
        use_kb: bool = True,
        with_check: bool = True,
    ) -> dict:
        stages = [s for s in (stages or STAGES) if s in STAGES]
        with self._session() as db:
            task = db.get(Task, task_id)
            if task is None:
                raise ValueError(f"task not found: {task_id}")
            if task.status == "processing":
                return {"task_id": task_id, "status": "processing"}
            task.status = "processing"
            task.error_message = ""
            task.mode = mode
            task.completed_at = None
            self._publish(db, task, 0, "任务已进入处理队列", "processing")

        try:
            for stage in stages:
                if stage == "preprocess":
                    self._run_preprocess(task_id)
                elif stage == "extract":
                    self._run_extract(task_id, mode)
                elif stage == "generate":
                    self._run_generate(task_id, industry, use_kb)
                elif stage == "check":
                    self._run_check(task_id)

            with self._session() as db:
                task = db.get(Task, task_id)
                task.status = "completed"
                task.progress = 100
                task.message = "全流程处理完成"
                task.completed_at = _now()
                db.commit()
                hub.publish(task_id, {"progress": 100, "message": "全流程处理完成", "status": "completed", "stage": task.current_stage})
            logger.info("pipeline completed task=%s", task_id)
            return {"task_id": task_id, "status": "completed"}
        except Exception as exc:
            logger.exception("pipeline failed task=%s", task_id)
            with self._session() as db:
                task = db.get(Task, task_id)
                task.status = "failed"
                task.error_message = f"{type(exc).__name__}: {exc}\n{traceback.format_exc()[-2000:]}"
                task.completed_at = _now()
                db.commit()
                hub.publish(task_id, {"progress": task.progress, "message": f"处理失败：{exc}", "status": "failed", "stage": task.current_stage})
            raise

    def _run_preprocess(self, task_id: str) -> None:
        with self._session() as db:
            task = db.get(Task, task_id)
            if task.manifest is not None:
                self._publish(db, task, 20, "预处理结果已存在，跳过")
                return
            task.current_stage = "preprocess"
            self._publish(db, task, 2, "正在解压并识别文件类型")

        def cb(progress: float, message: str) -> None:
            with self._session() as db:
                task = db.get(Task, task_id)
                self._publish(db, task, min(progress, 19), message)

        manifest = preprocess.run(task_id, cb)
        with self._session() as db:
            task = db.get(Task, task_id)
            task.manifest = manifest
            task.file_count = manifest.get("file_count", 0)
            task.current_stage = "extract"
            self._publish(db, task, 20, f"预处理完成，共处理 {task.file_count} 个文件")
        try:
            package_parser.parse_task_packages(task_id)
        except Exception as exc:
            logger.warning("标包解析失败（不影响主流程）：%s", exc)

    def _run_extract(self, task_id: str, mode: str) -> None:
        if not self._has_manifest(task_id):
            self._run_preprocess(task_id)
        with self._session() as db:
            task = db.get(Task, task_id)
            task.current_stage = "extract"
            self._publish(db, task, 22, f"正在抽取招标文件关键信息（{mode} 模式）")

        result = extractor.run(task_id, mode=mode, progress_cb=self._extract_cb(task_id))
        with self._session() as db:
            task = db.get(Task, task_id)
            task.extracted_data = result
            text = extractor.data_to_text(result)
            task.industry = detect_industry(text)
            result["knowledge_context"] = _build_knowledge_context(task_id, result, text, task.industry)
            task.extracted_data = result
            task.current_stage = "generate"
            self._publish(db, task, 55, f"信息抽取完成，行业识别为「{task.industry}」")

    def _extract_cb(self, task_id: str) -> ProgressCallback:
        def cb(progress: float, message: str) -> None:
            with self._session() as db:
                task = db.get(Task, task_id)
                self._publish(db, task, 22 + progress * 0.33, message)

        return cb

    def _run_generate(self, task_id: str, industry: str, use_kb: bool) -> None:
        if not self._has_extracted(task_id):
            self._run_extract(task_id, "fast")
        with self._session() as db:
            task = db.get(Task, task_id)
            task.current_stage = "generate"
            self._publish(db, task, 56, "正在生成投标文件初稿")

        result = generator.run(task_id, industry_override=industry, use_kb=use_kb)
        with self._session() as db:
            task = db.get(Task, task_id)
            task.bid_file_path = str(result["bid_file_path"])
            if result.get("industry"):
                task.industry = result["industry"]
            task.current_stage = "check"
            self._publish(db, task, 82, "投标文件生成完成，进入合规检查")

    def _run_check(self, task_id: str) -> None:
        if not task_has_field(task_id, "bid_file_path"):
            self._run_generate(task_id, "auto", True)
        with self._session() as db:
            task = db.get(Task, task_id)
            task.current_stage = "check"
            self._publish(db, task, 84, "正在执行合规检查与废标项检测")

        result = compliance.run(task_id)
        with self._session() as db:
            task = db.get(Task, task_id)
            task.check_result = result
            self._publish(db, task, 96, f"合规检查完成：{result['status']}")

    def _has_manifest(self, task_id: str) -> bool:
        with self._session() as db:
            task = db.get(Task, task_id)
            return bool(task and task.manifest)

    def _has_extracted(self, task_id: str) -> bool:
        with self._session() as db:
            task = db.get(Task, task_id)
            return bool(task and task.extracted_data)


def task_has_field(task_id: str, field: str) -> bool:
    with get_session_factory()() as db:
        task = db.get(Task, task_id)
        return bool(task and getattr(task, field))


def _build_knowledge_context(task_id: str, extracted: dict, text: str, industry: str) -> dict:
    """tender-extract 完成后构建 Obsidian 知识上下文摘要。"""
    try:
        from .kb_integration import get_gateway

        gateway = get_gateway()
        description = _primary_text(extracted, "project_name") or text[:500]
        context = gateway.get_context_for_bid(description, industry or "")
        summary = {
            "available": True,
            "similar_count": len(context.get("similar_projects", [])),
            "qualification_count": len(context.get("qualifications", [])),
            "template_count": len(context.get("templates", [])),
            "policy_count": len(context.get("policies", [])),
            "top_similar": [
                {"path": item.get("path"), "score": item.get("score")}
                for item in context.get("similar_projects", [])[:3]
            ],
        }
        with get_session_factory()() as db:
            task = db.get(Task, task_id)
            if task is not None:
                out_dir = Path(task.work_dir) / "output" / "intermediates"
                out_dir.mkdir(parents=True, exist_ok=True)
                (out_dir / "knowledge_context.json").write_text(
                    json.dumps(context, ensure_ascii=False, indent=2, default=str),
                    encoding="utf-8",
                )
        return summary
    except Exception as exc:
        logger.warning("知识上下文构建失败（不影响主流程）：%s", exc)
        return {"available": False, "error": str(exc)}


def _primary_text(extracted: dict, field: str) -> str:
    item = extracted.get(field) or {}
    value = item.get("primary_value") if isinstance(item, dict) else None
    return str(value) if value else ""


class JobQueue:
    def __init__(self) -> None:
        self._executor = ThreadPoolExecutor(max_workers=4)
        self._celery_checked = False
        self._celery_available = False

    def enqueue(
        self,
        task_id: str,
        stages: list[str] | None = None,
        mode: str = "fast",
        industry: str = "auto",
        use_kb: bool = True,
        with_check: bool = True,
    ) -> None:
        if self._use_celery():
            from .celery_app import run_pipeline_task

            run_pipeline_task.delay(task_id, stages, mode, industry, use_kb, with_check)
            return
        self._executor.submit(
            PipelineRunner().run,
            task_id=task_id,
            stages=stages,
            mode=mode,
            industry=industry,
            use_kb=use_kb,
            with_check=with_check,
        )

    def _use_celery(self) -> bool:
        if self.settings.system_env == "development" and not self.settings.redis_url:
            return False
        if not self._celery_checked:
            try:
                import redis

                client = redis.from_url(self.settings.redis_url, socket_connect_timeout=0.5)
                self._celery_available = bool(client.ping())
            except Exception:
                self._celery_available = False
            self._celery_checked = True
        return self._celery_available

    @property
    def settings(self):
        return get_settings()


queue = JobQueue()
