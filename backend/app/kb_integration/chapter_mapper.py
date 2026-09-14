"""章节知识映射器（方案 A + B）。

方案 A：章节标题关键词 → 知识库目录/标签规则；
方案 B：对每个章节构建检索词，用语义检索（Pinakes）或关键词检索兜底召回。
"""
from __future__ import annotations

import logging

from .file_handler import extract_tags, extract_wikilinks, resolve_wikilink
from .gateway import UnifiedKnowledgeGateway
from .rules_store import get_chapter_rules

logger = logging.getLogger(__name__)


class ChapterKnowledgeMapper:
    def __init__(self, rules: list[dict] | None = None) -> None:
        self.rules = rules or self._load_rules()

    @staticmethod
    def _load_rules() -> list[dict]:
        return get_chapter_rules()

    def match_chapter(self, title: str) -> dict | None:
        for rule in self.rules:
            if any(keyword in title for keyword in rule.get("keywords", [])):
                return rule
        return None

    def build_query(self, title: str, rule: dict, extracted: dict, industry: str) -> str:
        parts = [rule.get("query", ""), industry or ""]
        for field in ("project_name", "technical_requirements", "qualifications", "performance_requirements"):
            item = extracted.get(field) if isinstance(extracted, dict) else None
            if isinstance(item, dict):
                value = item.get("primary_value")
                if isinstance(value, list):
                    parts.extend(str(v) for v in value[:3])
                elif value:
                    parts.append(str(value)[:120])
        return " ".join(part for part in parts if part).strip() or title

    def retrieve_for_chapter(
        self,
        title: str,
        extracted: dict,
        industry: str,
        gateway: UnifiedKnowledgeGateway,
    ) -> list[dict]:
        rule = self.match_chapter(title)
        if rule is None:
            return []
        items: dict[str, dict] = {}

        for subdir in rule.get("directories", []):
            for rel in gateway.list_notes(subdir=subdir):
                try:
                    note = gateway.read_note(rel)
                except (FileNotFoundError, ValueError):
                    continue
                tags = extract_tags(note["content"], note["metadata"])
                if rule.get("tags") and not any(tag in tags for tag in rule["tags"]):
                    continue
                if not self._matches_frontmatter(note["metadata"], rule):
                    continue
                items[rel] = {
                    "path": rel,
                    "score": 1.0,
                    "content": note["content"][:2000],
                    "metadata": note["metadata"],
                    "source": "目录",
                }

        for tag in rule.get("tags", []):
            for rel in gateway.search_by_tag(tag):
                if rel in items:
                    continue
                if rule.get("directories") and not any(
                    rel.startswith(f"{directory.rstrip('/')}/") for directory in rule["directories"]
                ):
                    continue
                try:
                    note = gateway.read_note(rel)
                except (FileNotFoundError, ValueError):
                    continue
                if not self._matches_frontmatter(note["metadata"], rule):
                    continue
                items[rel] = {
                    "path": rel,
                    "score": 0.9,
                    "content": note["content"][:2000],
                    "metadata": note["metadata"],
                    "source": f"标签：{tag}",
                }

        query = self.build_query(title, rule, extracted, industry)
        if query:
            result = gateway.semantic_search(query, limit=5)
            for hit in result.get("results", []):
                rel = hit.get("path", "")
                if not rel:
                    continue
                score = float(hit.get("score", 0.5) or 0.5)
                if rel in items:
                    items[rel]["score"] = max(items[rel]["score"], score)
                    continue
                if rule.get("directories") and not any(
                    rel.startswith(f"{directory.rstrip('/')}/") for directory in rule["directories"]
                ):
                    continue
                note = self._read_note(gateway, rel)
                if note is None:
                    continue
                tags = extract_tags(note["content"], note["metadata"])
                if rule.get("tags") and not any(tag in tags for tag in rule["tags"]):
                    continue
                if not self._matches_frontmatter(note["metadata"], rule):
                    continue
                items[rel] = {
                    "path": rel,
                    "score": score,
                    "content": note["content"][:2000],
                    "metadata": note["metadata"],
                    "source": "语义检索",
                }

        self._expand_wikilinks(gateway, items)
        ranked = sorted(items.values(), key=lambda item: item["score"], reverse=True)
        return ranked[: rule.get("max_items", 3)]

    @staticmethod
    def _matches_frontmatter(metadata: dict, rule: dict) -> bool:
        pairs = rule.get("frontmatter") or []
        for pair in pairs:
            key, _, expected = str(pair).partition(":")
            key = key.strip()
            expected = expected.strip()
            if not key or not expected:
                continue
            value = metadata.get(key)
            if value is None:
                return False
            values = value if isinstance(value, list) else [value]
            if not any(expected in str(item) for item in values):
                return False
        return True

    def _expand_wikilinks(self, gateway: UnifiedKnowledgeGateway, items: dict[str, dict]) -> None:
        """命中笔记的 [[WikiLink]] 与 Frontmatter related 关联笔记也一并纳入。"""
        related_names: dict[str, float] = {}
        for item in items.values():
            note = self._read_note(gateway, item["path"])
            if note is None:
                continue
            for link in extract_wikilinks(note["content"]):
                related_names.setdefault(link, max(related_names.get(link, 0), float(item["score"]) * 0.8))
            raw_related = note["metadata"].get("related")
            if isinstance(raw_related, str):
                for link in [part.strip() for part in raw_related.split(",") if part.strip()]:
                    related_names.setdefault(link, max(related_names.get(link, 0), float(item["score"]) * 0.8))
            elif isinstance(raw_related, list):
                for link in [str(part).strip() for part in raw_related if str(part).strip()]:
                    related_names.setdefault(link, max(related_names.get(link, 0), float(item["score"]) * 0.8))

        for name, score in related_names.items():
            rel = resolve_wikilink(gateway.root, name)
            if not rel or rel in items:
                continue
            note = self._read_note(gateway, rel)
            if note is None:
                continue
            items[rel] = {
                "path": rel,
                "score": round(score, 4),
                "content": note["content"][:2000],
                "metadata": note["metadata"],
                "source": "WikiLink关联",
            }

    @staticmethod
    def _read_note(gateway: UnifiedKnowledgeGateway, rel: str) -> dict | None:
        try:
            return gateway.read_note(rel)
        except (FileNotFoundError, ValueError):
            return None

    def build_chapter_map(
        self,
        chapters: list[tuple[str, list]],
        extracted: dict,
        industry: str,
        gateway: UnifiedKnowledgeGateway,
    ) -> dict[str, list[dict]]:
        result: dict[str, list[dict]] = {}
        for title, _ in chapters:
            items = self.retrieve_for_chapter(title, extracted, industry, gateway)
            if items:
                result[title] = items
        return result


def format_knowledge_items(items: list[dict]) -> str:
    lines: list[str] = []
    for item in items:
        lines.append(f"来源：{item.get('path')}（{item.get('source', '')}）")
        content = str(item.get("content", "")).strip()
        if content:
            lines.append(content)
        lines.append("")
    return "\n".join(lines).strip()
