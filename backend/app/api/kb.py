from __future__ import annotations

import uuid
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile
from sqlalchemy.orm import Session

from ..audit import log_action
from ..config import get_settings
from ..database import get_db
from ..models import IndustryTemplate, KbDocument, KbType
from ..modules.knowledge import BUILTIN_KB_TYPES, KnowledgeService, classify_document, get_valid_types, process_attachment
from ..schemas import KbDocumentIn, KbDocumentOut, KbDocumentUpdate, KbSearchResponse, KbSearchResult, KbTypeIn, KbTypeOut
from ..security import get_current_user, rate_limit

router = APIRouter(prefix="/kb", tags=["知识库"])


def _to_out(doc: KbDocument) -> KbDocumentOut:
    return KbDocumentOut(
        id=doc.id,
        title=doc.title,
        content=doc.content,
        doc_type=doc.doc_type,
        metadata=doc.metadata_json,
        file_path=doc.file_path,
        created_at=doc.created_at,
        updated_at=doc.updated_at,
    )


@router.get("/documents", response_model=list[KbDocumentOut])
def list_documents(
    db: Annotated[Session, Depends(get_db)],
    user=Depends(get_current_user),
    doc_type: str | None = Query(None),
    limit: int = Query(100, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> list[KbDocumentOut]:
    service = KnowledgeService(db)
    _, items = service.list_documents(doc_type=doc_type, limit=limit, offset=offset)
    return [_to_out(item) for item in items]


@router.post("/documents", response_model=KbDocumentOut, dependencies=[Depends(rate_limit)])
def add_document(
    payload: KbDocumentIn,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user=Depends(get_current_user),
) -> KbDocumentOut:
    valid_types = get_valid_types(db)
    if payload.doc_type not in valid_types:
        raise HTTPException(status_code=422, detail=f"doc_type 必须是 {sorted(valid_types)} 之一")
    service = KnowledgeService(db)
    metadata = dict(payload.metadata or {})
    if payload.directory:
        metadata["obsidian_dir"] = payload.directory
    if payload.tags:
        metadata["tags"] = list(payload.tags)
    doc = service.add_document(payload.title, payload.content, payload.doc_type, metadata, payload.file_path)
    log_action(db, user.id, "kb_add", payload.title, {"doc_id": doc.id, "doc_type": payload.doc_type}, request)
    return _to_out(doc)


@router.post("/upload", response_model=KbDocumentOut, dependencies=[Depends(rate_limit)])
async def upload_attachment(
    request: Request,
    file: Annotated[UploadFile, File(description="知识库附件：PDF/DOCX/图片/表格/文本")],
    db: Annotated[Session, Depends(get_db)],
    user=Depends(get_current_user),
    doc_type: str = Form("auto"),
    title: str = Form(""),
    directory: str = Form(""),
    tags: str = Form(""),
) -> KbDocumentOut:
    settings = get_settings()
    original_name = Path(file.filename or "attachment").name
    doc_id = str(uuid.uuid4())
    upload_dir = settings.kb_path / "files"
    upload_dir.mkdir(parents=True, exist_ok=True)
    target = upload_dir / f"{doc_id}{Path(original_name).suffix.lower()}"

    with open(target, "wb") as fp:
        while True:
            chunk = await file.read(1024 * 1024)
            if not chunk:
                break
            fp.write(chunk)
    await file.close()

    processed = process_attachment(target, doc_id)
    detected_type, chapter = classify_document(title or original_name, processed["content"])
    if doc_type != "auto":
        valid_types = get_valid_types(db)
        detected_type = doc_type if doc_type in valid_types else "企业资质"
    kb_type = db.query(KbType).filter(KbType.name == detected_type).first()
    if kb_type is not None and kb_type.chapter != "通用":
        chapter = kb_type.chapter

    service = KnowledgeService(db)
    metadata_extra: dict = {}
    if directory:
        metadata_extra["obsidian_dir"] = directory
    if tags:
        metadata_extra["tags"] = [tag.strip() for tag in tags.replace("，", ",").split(",") if tag.strip()]
    doc = service.add_attachment(
        title=title or Path(original_name).stem,
        content=processed["content"],
        doc_type=detected_type,
        file_path=str(target),
        chapter=chapter,
        images=processed["images"],
        page_count=processed["page_count"],
        original_name=original_name,
        metadata_extra=metadata_extra,
    )
    log_action(
        db,
        user.id,
        "kb_upload",
        original_name,
        {"doc_id": doc.id, "doc_type": detected_type, "chapter": chapter, "file_size": target.stat().st_size},
        request,
    )
    return _to_out(doc)


@router.put("/documents/{doc_id}", response_model=KbDocumentOut)
def update_document(
    doc_id: str,
    payload: KbDocumentUpdate,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user=Depends(get_current_user),
) -> KbDocumentOut:
    if payload.doc_type:
        valid_types = get_valid_types(db)
        if payload.doc_type not in valid_types:
            raise HTTPException(status_code=422, detail=f"doc_type 必须是 {sorted(valid_types)} 之一")
    service = KnowledgeService(db)
    payload_data = payload.model_dump(exclude_none=True)
    if payload.directory or payload.tags:
        metadata = dict(payload_data.get("metadata") or {})
        if payload.directory:
            metadata["obsidian_dir"] = payload.directory
        if payload.tags is not None:
            metadata["tags"] = list(payload.tags)
        payload_data["metadata"] = metadata
    doc = service.update_document(doc_id, payload_data)
    if doc is None:
        raise HTTPException(status_code=404, detail="知识库文档不存在")
    log_action(db, user.id, "kb_update", doc_id, {}, request)
    return _to_out(doc)


@router.delete("/documents/{doc_id}")
def delete_document(
    doc_id: str,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user=Depends(get_current_user),
) -> dict:
    service = KnowledgeService(db)
    if not service.delete_document(doc_id):
        raise HTTPException(status_code=404, detail="知识库文档不存在")
    log_action(db, user.id, "kb_delete", doc_id, {}, request)
    return {"ok": True}


@router.get("/search", response_model=KbSearchResponse)
def search(
    db: Annotated[Session, Depends(get_db)],
    user=Depends(get_current_user),
    q: str = Query(..., min_length=1),
    top_k: int = Query(5, ge=1, le=20),
) -> KbSearchResponse:
    service = KnowledgeService(db)
    results = service.search(q, top_k=top_k)
    return KbSearchResponse(
        query=q,
        results=[KbSearchResult(**result) for result in results],
    )


@router.get("/types", response_model=list[KbTypeOut])
def list_kb_types(
    db: Annotated[Session, Depends(get_db)],
    user=Depends(get_current_user),
) -> list[KbTypeOut]:
    service = KnowledgeService(db)
    return [
        KbTypeOut(
            id=item.id,
            name=item.name,
            chapter=item.chapter,
            description=item.description,
            builtin=item.name in BUILTIN_KB_TYPES,
        )
        for item in service.list_kb_types()
    ]


@router.post("/types", response_model=KbTypeOut, dependencies=[Depends(rate_limit)])
def create_kb_type(
    payload: KbTypeIn,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user=Depends(get_current_user),
) -> KbTypeOut:
    if payload.chapter not in {"商务文件", "技术文件", "通用"}:
        raise HTTPException(status_code=422, detail="chapter 必须是 商务文件/技术文件/通用")
    service = KnowledgeService(db)
    kb_type = service.add_kb_type(payload.name, payload.chapter, payload.description)
    log_action(db, user.id, "kb_type_add", payload.name, {"chapter": payload.chapter}, request)
    return KbTypeOut(
        id=kb_type.id,
        name=kb_type.name,
        chapter=kb_type.chapter,
        description=kb_type.description,
        builtin=kb_type.name in BUILTIN_KB_TYPES,
    )


@router.delete("/types/{kb_type_id}")
def delete_kb_type(
    kb_type_id: str,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user=Depends(get_current_user),
) -> dict:
    service = KnowledgeService(db)
    existing = service.db.get(KbType, kb_type_id)
    if existing is not None and existing.name in BUILTIN_KB_TYPES:
        raise HTTPException(status_code=400, detail="内置类型不可删除")
    if not service.delete_kb_type(kb_type_id):
        raise HTTPException(status_code=404, detail="知识库类型不存在")
    log_action(db, user.id, "kb_type_delete", kb_type_id, {}, request)
    return {"ok": True}


@router.get("/templates")
def list_templates(db: Annotated[Session, Depends(get_db)], user=Depends(get_current_user)) -> list[dict]:
    templates = db.query(IndustryTemplate).filter(IndustryTemplate.is_active.is_(True)).order_by(IndustryTemplate.industry).all()
    return [
        {
            "id": t.id,
            "industry": t.industry,
            "name": t.name,
            "description": t.description,
            "version": t.version,
        }
        for t in templates
    ]
