from __future__ import annotations

import uuid
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile
from sqlalchemy.orm import Session

from ..audit import log_action
from ..config import get_settings
from ..database import get_db
from ..models import Task
from ..pipeline import queue
from ..schemas import TaskOut
from ..security import get_current_user, rate_limit

router = APIRouter(prefix="/preprocess", tags=["预处理"])

ALLOWED_SUFFIXES = {".zip", ".rar", ".7z", ".tar", ".gz", ".tgz", ".tar.gz", ".pdf", ".docx", ".doc", ".txt", ".md", ".markdown", ".xlsx", ".xls", ".csv", ".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff"}


@router.post("", response_model=TaskOut, dependencies=[Depends(rate_limit)])
async def preprocess(
    request: Request,
    file: Annotated[UploadFile, File(description="招标文件压缩包或单文件")],
    db: Annotated[Session, Depends(get_db)],
    user=Depends(get_current_user),
    auto_run: bool = Query(False, description="上传后自动执行全流程"),
    mode: str = Query("fast", pattern="^(fast|precise)$"),
    use_kb: bool = Query(True),
    with_check: bool = Query(True),
    source: str = Query("workbench", pattern="^(workbench|bid_special)$", description="任务来源工作区"),
) -> Task:
    settings = get_settings()
    original_name = Path(file.filename or "upload").name
    suffix = Path(original_name).suffix.lower()
    if suffix not in ALLOWED_SUFFIXES and not original_name.lower().endswith((".tar.gz", ".tar.bz2")):
        raise HTTPException(status_code=415, detail="请上传 .zip/.rar/.7z/.tar.gz 压缩包或 PDF/DOCX/文本/表格文件")

    task_id = str(uuid.uuid4())
    work_dir = settings.tasks_dir / task_id
    input_dir = work_dir / "input"
    input_dir.mkdir(parents=True, exist_ok=True)
    target_path = input_dir / original_name

    size = 0
    with open(target_path, "wb") as fp:
        while True:
            chunk = await file.read(1024 * 1024)
            if not chunk:
                break
            size += len(chunk)
            if size > settings.max_file_size:
                fp.close()
                target_path.unlink(missing_ok=True)
                raise HTTPException(status_code=413, detail=f"文件超过 {settings.max_file_size // 1024 // 1024} MB 限制")
            fp.write(chunk)
    await file.close()

    task = Task(
        id=task_id,
        user_id=user.id,
        status="queued",
        current_stage="preprocess",
        progress=0,
        original_file_name=original_name,
        original_file_path=str(target_path),
        work_dir=str(work_dir),
        message="文件已上传，等待处理",
        source=source,
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    if auto_run:
        from ..pipeline import STAGES

        queue.enqueue(task_id, STAGES, mode=mode, use_kb=use_kb, with_check=with_check)
    else:
        queue.enqueue(task_id, stages=["preprocess"])
    log_action(db, user.id, "file_upload", original_name, {"file_size": size, "task_id": task_id}, request)
    return task
