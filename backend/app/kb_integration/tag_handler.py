"""标签/目录检索引擎。"""
from __future__ import annotations

from pathlib import Path

from .file_handler import extract_tags, list_notes, read_note


def search_by_tag(root: Path, tag: str, subdir: str = "") -> list[str]:
    """返回包含指定标签的笔记相对路径。"""
    target = str(tag).strip().lstrip("#")
    if not target:
        return []
    hits: list[str] = []
    for rel in list_notes(root, subdir=subdir):
        try:
            note = read_note(root, rel)
        except (FileNotFoundError, ValueError):
            continue
        tags = extract_tags(note.content, note.metadata)
        if any(item == target or item.endswith("/" + target) for item in tags):
            hits.append(rel)
    return hits


def list_tags(root: Path, subdir: str = "") -> dict[str, int]:
    """统计知识库中所有标签的出现次数。"""
    counts: dict[str, int] = {}
    for rel in list_notes(root, subdir=subdir):
        try:
            note = read_note(root, rel)
        except (FileNotFoundError, ValueError):
            continue
        for tag in extract_tags(note.content, note.metadata):
            counts[tag] = counts.get(tag, 0) + 1
    return counts


def filter_by_tags(root: Path, subdir: str = "", tags: list[str] | None = None) -> list[str]:
    """目录 + 标签组合检索。"""
    if not tags:
        return list_notes(root, subdir=subdir)
    results = list_notes(root, subdir=subdir)
    wanted = {str(tag).strip().lstrip("#") for tag in tags if str(tag).strip()}
    filtered: list[str] = []
    for rel in results:
        try:
            note = read_note(root, rel)
        except (FileNotFoundError, ValueError):
            continue
        found = extract_tags(note.content, note.metadata)
        if wanted.intersection(found):
            filtered.append(rel)
    return filtered
