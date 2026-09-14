"""标书知识上下文构建器。"""
from __future__ import annotations

import re
from pathlib import Path

from .config import KnowledgeBaseConfig
from .file_handler import list_notes, read_note
from .pinakes_adapter import PinakesAdapter

STOPWORDS = {
    "的", "了", "是", "在", "等", "和", "与", "或", "及", "为", "对", "中", "有",
    "项目", "招标", "投标", "采购", "要求", "本", "以及", "我们", "公司", "一个",
}
KEYWORD_RE = re.compile(r"[\u4e00-\u9fffA-Za-z0-9]{2,6}")


def extract_keywords(text: str, max_keywords: int = 5) -> list[str]:
    """从项目描述提取检索关键词，最多返回 max_keywords 个。"""
    if not text:
        return []
    counts: dict[str, int] = {}
    for match in KEYWORD_RE.findall(text):
        token = match
        if token in STOPWORDS:
            continue
        counts[token] = counts.get(token, 0) + 1
    ranked = sorted(counts.items(), key=lambda item: (item[1], len(item[0])), reverse=True)
    keywords = [word for word, _ in ranked if word not in STOPWORDS][:max_keywords]
    return keywords


class ContextBuilder:
    def __init__(self, config: KnowledgeBaseConfig, adapter: PinakesAdapter) -> None:
        self.config = config
        self.adapter = adapter

    def get_context_for_bid(self, project_description: str, industry: str = "") -> dict:
        root = Path(self.config.root_path)
        context: dict = {
            "similar_projects": [],
            "qualifications": [],
            "templates": [],
            "policies": [],
        }
        query = project_description or ""
        if not query:
            query = " ".join(extract_keywords(project_description or ""))
        if query:
            context["similar_projects"] = self.adapter.semantic_search(query, limit=3)
        context["qualifications"] = self._read_dir(root, self.config.dir("qualifications"), max_chars=2000)
        context["templates"] = self._read_templates(root, industry)
        context["policies"] = self._read_policies(root, industry)
        return context

    def _read_dir(self, root: Path, subdir: str, max_chars: int = 2000) -> list[dict]:
        items: list[dict] = []
        for rel in list_notes(root, subdir=subdir):
            try:
                note = read_note(root, rel)
            except (FileNotFoundError, ValueError):
                continue
            items.append(
                {
                    "path": rel,
                    "content": note.content[:max_chars],
                    "metadata": note.metadata,
                }
            )
        return items

    def _read_templates(self, root: Path, industry: str) -> list[dict]:
        base = self.config.dir("templates")
        candidates: list[str] = []
        if industry:
            candidates.append(f"{base}/{industry}")
        candidates.append(f"{base}/通用")
        candidates.append(base)
        seen: set[str] = set()
        items: list[dict] = []
        for subdir in candidates:
            for rel in list_notes(root, subdir=subdir):
                if rel in seen:
                    continue
                seen.add(rel)
                try:
                    note = read_note(root, rel)
                except (FileNotFoundError, ValueError):
                    continue
                items.append(
                    {
                        "path": rel,
                        "content": note.content[:3000],
                        "metadata": note.metadata,
                    }
                )
        return items

    def _read_policies(self, root: Path, industry: str) -> list[dict]:
        items: list[dict] = []
        for rel in list_notes(root, subdir=self.config.dir("policies")):
            try:
                note = read_note(root, rel)
            except (FileNotFoundError, ValueError):
                continue
            metadata_industry = str(note.metadata.get("industry", "") or "")
            text = f"{rel}\n{note.content}"
            if industry and metadata_industry and industry not in metadata_industry and metadata_industry not in industry:
                continue
            if industry and not metadata_industry and industry not in text:
                continue
            items.append(
                {
                    "path": rel,
                    "content": note.content[:2000],
                    "metadata": note.metadata,
                }
            )
        return items
