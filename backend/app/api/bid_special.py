"""国网投标专项接口：专用知识映射规则。"""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from ..kb_integration import get_gateway
from ..kb_integration.bid_rules_store import (
    get_bid_chapter_rules,
    reset_bid_chapter_rules,
    save_bid_chapter_rules,
)
from ..kb_integration.chapter_mapper import ChapterKnowledgeMapper
from ..security import get_current_user

router = APIRouter(prefix="/bid-special", tags=["国网投标专项"])


class BidChapterRuleIn(BaseModel):
    keywords: list[str] = Field(default_factory=list)
    directories: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    frontmatter: list[str] = Field(default_factory=list)
    query: str = ""
    max_items: int = Field(3, ge=1, le=20)


class BidChapterRulesIn(BaseModel):
    rules: list[BidChapterRuleIn] = Field(default_factory=list)


class BidChapterRulePreviewIn(BidChapterRuleIn):
    chapter_title: str | None = None


@router.get("/chapter-rules")
def bid_chapter_rules(user=Depends(get_current_user)) -> dict:
    return {"scope": "bid_special", "rules": get_bid_chapter_rules()}


@router.put("/chapter-rules")
def update_bid_chapter_rules(payload: BidChapterRulesIn, user=Depends(get_current_user)) -> dict:
    rules = [rule.model_dump() for rule in payload.rules]
    return {"scope": "bid_special", "rules": save_bid_chapter_rules(rules)}


@router.post("/chapter-rules/reset")
def reset_bid_chapter_rules_endpoint(user=Depends(get_current_user)) -> dict:
    return {"scope": "bid_special", "rules": reset_bid_chapter_rules()}


@router.post("/chapter-rules/preview")
def preview_bid_chapter_rule(payload: BidChapterRulePreviewIn, user=Depends(get_current_user)) -> dict:
    gateway = get_gateway()
    mapper = ChapterKnowledgeMapper([payload.model_dump()])
    title = payload.chapter_title or (payload.keywords[0] if payload.keywords else "测试章节")
    items = mapper.retrieve_for_chapter(title, {}, "", gateway)
    return {"title": title, "items": items}
