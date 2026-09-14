"""Markdown 文件读写引擎。

兼容 Obsidian：Frontmatter 解析/写入、WikiLink 识别、标签提取。
所有路径经过规范化校验，拒绝 ``..`` 越权。
"""
from __future__ import annotations

import logging
import posixpath
import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)

WIKILINK_RE = re.compile(r"\[\[([^\]]+)\]\]")
TAG_RE = re.compile(r"(?<![\w#])#([\w/_-]+)")
SYNC_CONFLICT_MARK = "sync-conflict"
IGNORED_DIRS = {".obsidian", ".pinakes_index", ".trash", ".git"}


@dataclass
class Note:
    path: str
    content: str = ""
    metadata: dict = field(default_factory=dict)


def parse_note(text: str) -> tuple[dict, str]:
    """解析 Obsidian Markdown，返回 (metadata, content)。"""
    if not text.startswith("---"):
        return {}, text
    lines = text.splitlines()
    end = None
    for index in range(1, len(lines)):
        if lines[index].strip() == "---":
            end = index
            break
    if end is None:
        return {}, text
    block = "\n".join(lines[1:end])
    metadata: dict = {}
    try:
        parsed = yaml.safe_load(block)
        if isinstance(parsed, dict):
            metadata = parsed
    except Exception as exc:
        logger.warning("Frontmatter 解析失败，按正文处理：%s", exc)
    return metadata, "\n".join(lines[end + 1 :]).lstrip("\n")


def render_note(content: str, metadata: dict | None = None) -> str:
    """序列化为 Obsidian 兼容 Markdown。"""
    metadata = metadata or {}
    if not metadata:
        return content
    try:
        block = yaml.safe_dump(metadata, allow_unicode=True, sort_keys=False).strip()
    except Exception:
        block = yaml.safe_dump(dict(metadata), allow_unicode=True, sort_keys=False).strip()
    return f"---\n{block}\n---\n\n{content}"


def safe_relative_path(rel_path: str) -> str:
    """规范化相对路径并拒绝越权。"""
    clean = rel_path.replace("\\", "/")
    normalized = posixpath.normpath(clean)
    if normalized in {".", ""} or normalized.startswith("../") or normalized.startswith("/") or ":" in normalized.split("/")[0]:
        raise ValueError(f"非法知识库路径：{rel_path}")
    return normalized


def resolve_path(root: Path, rel_path: str) -> Path:
    normalized = safe_relative_path(rel_path)
    target = (Path(root) / normalized).resolve()
    root_resolved = Path(root).resolve()
    if not target.is_relative_to(root_resolved):
        raise ValueError(f"路径越权：{rel_path}")
    return target


def _read_bytes(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        try:
            return path.read_text(encoding="gbk", errors="replace")
        except Exception:
            return path.read_text(encoding="utf-8", errors="replace")


def read_note(root: Path, rel_path: str) -> Note:
    target = resolve_path(root, rel_path)
    if not target.exists():
        raise FileNotFoundError(f"笔记不存在：{rel_path}")
    text = _read_bytes(target)
    metadata, content = parse_note(text)
    return Note(path=safe_relative_path(rel_path), content=content, metadata=metadata)


def write_note(root: Path, rel_path: str, content: str, metadata: dict | None = None) -> Note:
    normalized = safe_relative_path(rel_path)
    if not normalized.endswith(".md"):
        normalized += ".md"
    target = resolve_path(root, normalized)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(render_note(content, metadata or {}), encoding="utf-8")
    return Note(path=normalized, content=content, metadata=metadata or {})


def list_notes(root: Path, subdir: str = "", extension: str = ".md") -> list[str]:
    """递归列出知识库内笔记相对路径，忽略 Obsidian/Pinakes 与冲突文件。"""
    base = resolve_path(root, subdir) if subdir else Path(root).resolve()
    if not base.exists():
        return []
    results: list[str] = []
    for file_path in sorted(base.rglob(f"*{extension}")):
        if not file_path.is_file():
            continue
        parts = file_path.relative_to(Path(root).resolve()).parts
        if any(part in IGNORED_DIRS for part in parts):
            continue
        if SYNC_CONFLICT_MARK in file_path.name:
            continue
        results.append(posixpath.join(*parts))
    return results


def extract_tags(content: str, metadata: dict | None = None) -> list[str]:
    """合并 Frontmatter tags 与正文 #tag，去重保序。"""
    tags: list[str] = []
    raw = (metadata or {}).get("tags", [])
    if isinstance(raw, str):
        raw = [raw]
    for tag in raw or []:
        value = str(tag).strip().lstrip("#")
        if value and value not in tags:
            tags.append(value)
    for tag in TAG_RE.findall(content):
        if tag not in tags:
            tags.append(tag)
    return tags


def extract_wikilinks(content: str) -> list[str]:
    """提取 [[笔记名]]，返回去重后的笔记名列表。"""
    links: list[str] = []
    for match in WIKILINK_RE.findall(content):
        name = match.split("|", 1)[0].strip()
        if name and name not in links:
            links.append(name)
    return links


def resolve_wikilink(root: Path, name: str) -> str | None:
    """把 [[笔记名]] 解析为知识库内的相对路径，找不到返回 None。"""
    clean = str(name).strip()
    if clean.startswith("[[") and clean.endswith("]]"):
        clean = clean[2:-2]
    clean = clean.split("|", 1)[0].strip().lstrip("/")
    if not clean:
        return None
    candidates = [clean, f"{clean}.md"]
    for rel in list_notes(root):
        if rel in candidates:
            return rel
        stem = posixpath.splitext(rel)[0]
        if stem == clean or stem.endswith("/" + clean):
            return rel
    return None
