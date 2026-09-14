from __future__ import annotations

import mimetypes
import shutil
import subprocess
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import FileResponse
from sqlalchemy import or_
from sqlalchemy.orm import Session

from ..audit import log_action
from ..database import get_db
from ..models import Task
from ..modules import package_bid, package_parser
from ..pipeline import STAGES, queue
from ..schemas import CheckRequest, ExtractRequest, GeneratePackageBidRequest, GenerateRequest, RunRequest, TaskListResponse, TaskOut
from ..security import get_current_user, require_role

router = APIRouter(tags=["任务"])


def _task_or_404(db: Session, task_id: str) -> Task:
    task = db.get(Task, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    return task


@router.get("/tasks", response_model=TaskListResponse)
def list_tasks(
    db: Annotated[Session, Depends(get_db)],
    user=Depends(get_current_user),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    status_filter: str | None = Query(None, alias="status"),
    source_filter: str | None = Query(None, alias="source", description="任务来源工作区"),
) -> TaskListResponse:
    query = db.query(Task)
    if user.role != "管理员":
        query = query.filter(Task.user_id == user.id)
    if status_filter:
        query = query.filter(Task.status == status_filter)
    if source_filter:
        if source_filter == "workbench":
            query = query.filter(or_(Task.source == "workbench", Task.source.is_(None)))
        else:
            query = query.filter(Task.source == source_filter)
    total = query.count()
    items = query.order_by(Task.created_at.desc()).offset(offset).limit(limit).all()
    return TaskListResponse(total=total, items=[TaskOut.model_validate(item, from_attributes=True) for item in items])


@router.get("/tasks/{task_id}", response_model=TaskOut)
def get_task(task_id: str, db: Annotated[Session, Depends(get_db)], user=Depends(get_current_user)) -> Task:
    task = _task_or_404(db, task_id)
    if user.role != "管理员" and task.user_id != user.id:
        raise HTTPException(status_code=403, detail="无权访问该任务")
    if task.extracted_data:
        from ..modules.reference_resolver import enrich_missing_fields, resolve_references

        enrich_missing_fields(task_id, task.extracted_data)
        resolve_references(task_id, task.extracted_data)
        db.add(task)
        db.commit()
    return task


@router.post("/tasks/{task_id}/run", response_model=TaskOut)
def run_task(
    task_id: str,
    payload: RunRequest,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user=Depends(get_current_user),
) -> Task:
    task = _task_or_404(db, task_id)
    if user.role != "管理员" and task.user_id != user.id:
        raise HTTPException(status_code=403, detail="无权操作该任务")
    if task.status == "processing":
        raise HTTPException(status_code=409, detail="任务正在处理中")
    task.status = "queued"
    task.mode = payload.mode
    db.commit()
    queue.enqueue(task_id, STAGES, payload.mode, payload.industry, payload.use_kb, payload.with_check)
    log_action(db, user.id, "run_pipeline", task_id, payload.model_dump(), request)
    return task


@router.post("/extract", response_model=TaskOut)
def extract(
    payload: ExtractRequest,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user=Depends(get_current_user),
) -> Task:
    task = _task_or_404(db, payload.task_id)
    if user.role != "管理员" and task.user_id != user.id:
        raise HTTPException(status_code=403, detail="无权操作该任务")
    if task.status == "processing":
        raise HTTPException(status_code=409, detail="任务正在处理中")
    task.status = "queued"
    task.mode = payload.mode
    db.commit()
    queue.enqueue(payload.task_id, ["extract"], mode=payload.mode)
    log_action(db, user.id, "extract", payload.task_id, {"mode": payload.mode}, request)
    return task


@router.post("/generate", response_model=TaskOut)
def generate(
    payload: GenerateRequest,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user=Depends(get_current_user),
) -> Task:
    task = _task_or_404(db, payload.task_id)
    if user.role != "管理员" and task.user_id != user.id:
        raise HTTPException(status_code=403, detail="无权操作该任务")
    if task.status == "processing":
        raise HTTPException(status_code=409, detail="任务正在处理中")
    task.status = "queued"
    db.commit()
    queue.enqueue(payload.task_id, ["generate"], industry=payload.industry, use_kb=payload.use_kb)
    log_action(db, user.id, "generate", payload.task_id, payload.model_dump(), request)
    return task


@router.post("/check", response_model=TaskOut)
def check(
    payload: CheckRequest,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user=Depends(get_current_user),
) -> Task:
    task = _task_or_404(db, payload.task_id)
    if user.role != "管理员" and task.user_id != user.id:
        raise HTTPException(status_code=403, detail="无权操作该任务")
    if task.status == "processing":
        raise HTTPException(status_code=409, detail="任务正在处理中")
    task.status = "queued"
    db.commit()
    queue.enqueue(payload.task_id, ["check"])
    log_action(db, user.id, "compliance_check", payload.task_id, {}, request)
    return task


@router.get("/tasks/{task_id}/packages")
def get_packages(
    task_id: str,
    db: Annotated[Session, Depends(get_db)],
    user=Depends(get_current_user),
) -> dict:
    task = _task_or_404(db, task_id)
    if user.role != "管理员" and task.user_id != user.id:
        raise HTTPException(status_code=403, detail="无权访问该任务")
    return package_parser.load_or_parse(task_id)


@router.post("/tasks/{task_id}/packages/parse")
def parse_packages(
    task_id: str,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user=Depends(get_current_user),
) -> dict:
    task = _task_or_404(db, task_id)
    if user.role != "管理员" and task.user_id != user.id:
        raise HTTPException(status_code=403, detail="无权操作该任务")
    result = package_parser.parse_task_packages(task_id)
    log_action(db, user.id, "parse_packages", task_id, {"packages": len(result.get("packages", []))}, request)
    return result


@router.post("/tasks/{task_id}/packages/{package_no}/generate")
def generate_package_bid_file(
    task_id: str,
    package_no: str,
    payload: GeneratePackageBidRequest,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user=Depends(get_current_user),
) -> dict:
    task = _task_or_404(db, task_id)
    if user.role != "管理员" and task.user_id != user.id:
        raise HTTPException(status_code=403, detail="无权操作该任务")
    try:
        result = package_bid.generate_package_bid(task_id, package_no, payload.files, subproject=payload.subproject)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    log_action(
        db,
        user.id,
        "generate_package_bid",
        task_id,
        {"package_no": package_no, "products": result.get("product_count", 0)},
        request,
    )
    return result


@router.get("/tasks/{task_id}/package-bid")
def download_package_bid_file(
    task_id: str,
    db: Annotated[Session, Depends(get_db)],
    user=Depends(get_current_user),
    path: str = Query(..., description="生成的投标文件路径"),
) -> FileResponse:
    task = _task_or_404(db, task_id)
    if user.role != "管理员" and task.user_id != user.id:
        raise HTTPException(status_code=403, detail="无权访问该任务")
    work_dir = Path(task.work_dir).resolve()
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = Path.cwd() / candidate
    target = candidate.resolve()
    if not target.is_relative_to(work_dir) or not target.exists():
        raise HTTPException(status_code=404, detail="投标文件不存在")
    return FileResponse(
        target,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        filename=target.name,
    )


@router.get("/tasks/{task_id}/package-file")
def package_file_content(
    task_id: str,
    db: Annotated[Session, Depends(get_db)],
    user=Depends(get_current_user),
    path: str = Query(..., description="标包文件 md_path"),
) -> dict:
    task = _task_or_404(db, task_id)
    if user.role != "管理员" and task.user_id != user.id:
        raise HTTPException(status_code=403, detail="无权访问该任务")
    work_dir = Path(task.work_dir).resolve()
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = Path.cwd() / candidate
    target = candidate.resolve()
    if not target.is_relative_to(work_dir) or not target.exists():
        raise HTTPException(status_code=404, detail="文件不存在")
    return {
        "name": target.name,
        "content": target.read_text(encoding="utf-8", errors="replace"),
    }


@router.get("/tasks/{task_id}/package-file/raw")
def package_file_raw(
    task_id: str,
    db: Annotated[Session, Depends(get_db)],
    user=Depends(get_current_user),
    path: str = Query(..., description="标包原始文件路径"),
) -> FileResponse:
    task = _task_or_404(db, task_id)
    if user.role != "管理员" and task.user_id != user.id:
        raise HTTPException(status_code=403, detail="无权访问该任务")
    work_dir = Path(task.work_dir).resolve()
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = Path.cwd() / candidate
    target = candidate.resolve()
    if not target.is_relative_to(work_dir) or not target.exists():
        raise HTTPException(status_code=404, detail="文件不存在")
    media_type = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
    return FileResponse(target, media_type=media_type, filename=target.name)


@router.get("/tasks/{task_id}/package-file/preview")
def package_file_preview(
    task_id: str,
    db: Annotated[Session, Depends(get_db)],
    user=Depends(get_current_user),
    path: str = Query(..., description="标包原始文件路径"),
) -> FileResponse:
    task = _task_or_404(db, task_id)
    if user.role != "管理员" and task.user_id != user.id:
        raise HTTPException(status_code=403, detail="无权访问该任务")
    work_dir = Path(task.work_dir).resolve()
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = Path.cwd() / candidate
    target = candidate.resolve()
    if not target.is_relative_to(work_dir) or not target.exists():
        raise HTTPException(status_code=404, detail="文件不存在")

    suffix = target.suffix.lower()
    if suffix == ".pdf":
        return FileResponse(target, media_type="application/pdf", filename=target.name)
    if suffix in {".docx", ".doc"}:
        pdf_path = _convert_doc_to_pdf(target, work_dir)
        return FileResponse(pdf_path, media_type="application/pdf", filename=f"{target.stem}.pdf")
    media_type = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
    return FileResponse(target, media_type=media_type, filename=target.name)


def _convert_doc_to_pdf(source: Path, work_dir: Path) -> Path:
    """将文档原样转为 PDF：优先 LibreOffice / Word，兼容 WPS 变体时回退 Pages。"""
    cache_dir = work_dir / "packages_preview"
    cache_dir.mkdir(parents=True, exist_ok=True)
    pdf_path = cache_dir / f"{source.stem}.pdf"
    if pdf_path.exists():
        return pdf_path

    soffice = shutil.which("soffice") or shutil.which("libreoffice")
    if not soffice:
        for candidate in (
            "/Applications/LibreOffice.app/Contents/MacOS/soffice",
            "/usr/local/bin/soffice",
            "/opt/homebrew/bin/soffice",
        ):
            if Path(candidate).exists():
                soffice = candidate
                break
    if soffice:
        subprocess.run(
            [soffice, "--headless", "--convert-to", "pdf", "--outdir", str(cache_dir), str(source)],
            check=True,
            capture_output=True,
            timeout=120,
        )
    else:
        try:
            _convert_with_word(source, pdf_path)
        except Exception:
            _convert_with_pages(source, pdf_path)
    if not pdf_path.exists():
        raise HTTPException(status_code=500, detail="文档转 PDF 失败：未生成 PDF")
    return pdf_path


def _convert_with_word(source: Path, pdf_path: Path) -> None:
    script = Path(__file__).resolve().parent.parent / "scripts" / "convert_word_to_pdf.jxa"
    result = subprocess.run(
        ["osascript", "-l", "JavaScript", str(script), str(source), str(pdf_path)],
        capture_output=True,
        text=True,
        timeout=120,
    )
    if result.returncode != 0 or not pdf_path.exists():
        raise RuntimeError(f"Word 转换失败：{result.stdout[-500:]}")


def _convert_with_pages(source: Path, pdf_path: Path) -> None:
    script = (
        'tell application "Pages"\n'
        f'  open POSIX file "{source}"\n'
        "  delay 8\n"
        "  set d to document 1\n"
        f'  export d to POSIX file "{pdf_path}" as PDF\n'
        "  close d saving no\n"
        "end tell"
    )
    result = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=120)
    if result.returncode != 0 or not pdf_path.exists():
        raise RuntimeError(f"Pages 转换失败：{result.stderr[-500:]}")


def _is_ole2_doc(path: Path) -> bool:
    """旧版二进制 Word（OLE2）文件，含伪装成 .docx 的情况。"""
    try:
        header = path.read_bytes()[:8]
    except OSError:
        return False
    return header == b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"


@router.delete("/tasks/{task_id}")
def delete_task(
    task_id: str,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user=Depends(require_role("管理员", "普通用户", "审核员")),
) -> dict:
    task = _task_or_404(db, task_id)
    if user.role != "管理员" and task.user_id != user.id:
        raise HTTPException(status_code=403, detail="无权删除该任务")
    work_dir = Path(task.work_dir)
    db.delete(task)
    db.commit()
    shutil.rmtree(work_dir, ignore_errors=True)
    log_action(db, user.id, "delete_task", task_id, {}, request)
    return {"ok": True}


@router.get("/download/{task_id}")
def download_bid(
    task_id: str,
    db: Annotated[Session, Depends(get_db)],
    user=Depends(get_current_user),
) -> FileResponse:
    task = _task_or_404(db, task_id)
    if user.role != "管理员" and task.user_id != user.id:
        raise HTTPException(status_code=403, detail="无权下载该任务")
    if not task.bid_file_path or not Path(task.bid_file_path).exists():
        raise HTTPException(status_code=404, detail="标书文件不存在")
    return FileResponse(
        task.bid_file_path,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        filename=f"{task.original_file_name or 'bid'}_{task_id[:8]}.docx",
    )
