"""Obsidian 知识库（文件系统）接口。"""
from __future__ import annotations

import posixpath
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from ..kb_integration import get_gateway
from ..kb_integration.chapter_mapper import ChapterKnowledgeMapper
from ..kb_integration.file_handler import IGNORED_DIRS
from ..kb_integration.rules_store import get_chapter_rules, save_chapter_rules
from ..security import get_current_user

router = APIRouter(prefix="/kb-files", tags=["Obsidian知识库"])


class NoteWriteIn(BaseModel):
    path: str = Field(..., min_length=1)
    content: str = ""
    metadata: dict | None = None


class ChapterRuleIn(BaseModel):
    keywords: list[str] = Field(default_factory=list)
    directories: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    frontmatter: list[str] = Field(default_factory=list, description="Frontmatter 字段匹配，如 industry:IT")
    query: str = ""
    max_items: int = Field(3, ge=1, le=20)


class ChapterRulesIn(BaseModel):
    rules: list[ChapterRuleIn] = Field(default_factory=list)


class ChapterRulePreviewIn(ChapterRuleIn):
    chapter_title: str | None = None


@router.get("/status")
def status(user=Depends(get_current_user)) -> dict:
    return get_gateway().status()


@router.get("/tree")
def tree(user=Depends(get_current_user)) -> list[dict]:
    gateway = get_gateway()
    return _build_tree(gateway.root)


@router.get("/note")
def read_note_endpoint(
    path: str = Query(..., min_length=1),
    user=Depends(get_current_user),
) -> dict:
    try:
        return get_gateway().read_note(path)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/note")
def write_note_endpoint(
    payload: NoteWriteIn,
    user=Depends(get_current_user),
) -> dict:
    try:
        return get_gateway().write_note(payload.path, payload.content, payload.metadata)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/search")
def search(
    q: str = Query(..., min_length=1),
    limit: int = Query(5, ge=1, le=20),
    user=Depends(get_current_user),
) -> dict:
    return get_gateway().semantic_search(q, limit=limit)


@router.get("/tags")
def tags(user=Depends(get_current_user)) -> dict:
    counts = get_gateway().list_tags()
    return {
        "tags": [{"tag": tag, "count": count} for tag, count in sorted(counts.items(), key=lambda item: item[1], reverse=True)]
    }


@router.get("/notes")
def notes(
    tag: str | None = Query(None),
    subdir: str | None = Query(None),
    user=Depends(get_current_user),
) -> dict:
    gateway = get_gateway()
    if tag:
        items = gateway.search_by_tag(tag, subdir=subdir or "")
    else:
        items = gateway.list_notes(subdir=subdir or "")
    return {"notes": items}


@router.post("/reindex")
def reindex(user=Depends(get_current_user)) -> dict:
    gateway = get_gateway()
    if not gateway.adapter.available:
        return {"ok": False, "engine": "keyword", "message": "Pinakes 二进制不存在，当前使用关键词检索"}
    ok = gateway.adapter.reindex()
    return {"ok": ok, "engine": "pinakes" if ok else "keyword"}


@router.get("/chapter-rules")
def chapter_rules(user=Depends(get_current_user)) -> dict:
    return {"rules": get_chapter_rules()}


@router.put("/chapter-rules")
def update_chapter_rules(payload: ChapterRulesIn, user=Depends(get_current_user)) -> dict:
    rules = [rule.model_dump() for rule in payload.rules]
    return {"rules": save_chapter_rules(rules)}


@router.get("/directories")
def directories(user=Depends(get_current_user)) -> dict:
    gateway = get_gateway()
    root = gateway.root
    result: list[str] = []
    for path in sorted(root.rglob("*")):
        if not path.is_dir():
            continue
        try:
            parts = path.relative_to(root).parts
        except ValueError:
            continue
        if any(part in IGNORED_DIRS or part.startswith(".") for part in parts):
            continue
        result.append(path.relative_to(root).as_posix())
    return {"directories": result}


@router.post("/chapter-rules/preview")
def preview_chapter_rule(payload: ChapterRulePreviewIn, user=Depends(get_current_user)) -> dict:
    gateway = get_gateway()
    mapper = ChapterKnowledgeMapper([payload.model_dump()])
    title = payload.chapter_title or (payload.keywords[0] if payload.keywords else "测试章节")
    items = mapper.retrieve_for_chapter(title, {}, "", gateway)
    return {"title": title, "items": items}


def _build_tree(root, base: str = "") -> list[dict]:
    current = root if not base else root / base
    if not current.exists():
        return []
    nodes: list[dict] = []
    for child in sorted(current.iterdir(), key=lambda item: (item.is_file(), item.name.lower())):
        rel = child.name if not base else posixpath.join(base, child.name)
        if child.is_dir():
            if child.name in IGNORED_DIRS or child.name.startswith("."):
                continue
            nodes.append({"name": child.name, "path": rel, "type": "dir", "children": _build_tree(root, rel)})
        elif child.suffix.lower() == ".md" and "sync-conflict" not in child.name:
            nodes.append({"name": child.name, "path": rel, "type": "file"})
    return nodes
