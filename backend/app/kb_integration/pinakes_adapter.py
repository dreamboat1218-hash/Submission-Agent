"""Pinakes 语义检索适配器。

通过子进程调用 Pinakes 命令行；二进制缺失、超时或解析失败时自动降级为
关键词匹配，保证核心检索功能不中断。
"""
from __future__ import annotations

import json
import logging
import os
import subprocess
import time
from pathlib import Path

from .config import KnowledgeBaseConfig
from .file_handler import list_notes, read_note

logger = logging.getLogger(__name__)


class PinakesAdapter:
    def __init__(self, config: KnowledgeBaseConfig) -> None:
        self.config = config

    @property
    def binary(self) -> Path:
        return Path(self.config.pinakes_bin)

    @property
    def available(self) -> bool:
        return self.binary.exists() and os_access(self.binary)

    @property
    def index_dir(self) -> Path:
        return Path(self.config.root_path) / ".pinakes_index"

    def init_index(self) -> bool:
        return self._run(["init"])

    def reindex(self) -> bool:
        return self._run(["reindex"])

    def _run(self, args: list[str]) -> bool:
        if not self.available:
            return False
        command = [str(self.binary), *args, "--path", str(self.config.root_path)]
        try:
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=self.config.search_timeout,
            )
            return result.returncode == 0
        except (OSError, subprocess.TimeoutExpired) as exc:
            logger.warning("Pinakes 命令执行失败 %s：%s", args, exc)
            return False

    def semantic_search(self, query: str, limit: int | None = None) -> list[dict]:
        """优先语义检索，失败时返回关键词检索结果（附带 engine 标记）。"""
        limit = limit or self.config.max_search_results
        if self.available:
            started = time.monotonic()
            command = [
                str(self.binary),
                "search",
                query,
                "--limit",
                str(limit),
                "--path",
                str(self.config.root_path),
                "--format",
                "json",
            ]
            try:
                result = subprocess.run(
                    command,
                    capture_output=True,
                    text=True,
                    timeout=self.config.search_timeout,
                )
                if result.returncode == 0:
                    results = self._parse_results(result.stdout)
                    if results is None:
                        logger.warning("Pinakes JSON 解析失败，降级到关键词检索")
                        return self.keyword_search(query, limit=limit)
                    logger.info(
                        "[KNOWLEDGE] 语义检索 | query=%s | results=%d | duration=%.0fms",
                        query,
                        len(results),
                        (time.monotonic() - started) * 1000,
                    )
                    return results
                logger.warning("Pinakes 返回码 %s，降级到关键词检索", result.returncode)
            except subprocess.TimeoutExpired:
                logger.warning("Pinakes 执行超时，降级到关键词检索")
            except OSError as exc:
                logger.warning("Pinakes 执行失败：%s", exc)
        return self.keyword_search(query, limit=limit)

    def _parse_results(self, stdout: str) -> list[dict]:
        try:
            raw = json.loads(stdout)
        except json.JSONDecodeError:
            return None
        items = raw if isinstance(raw, list) else raw.get("results", [])
        results: list[dict] = []
        for item in items or []:
            if not isinstance(item, dict):
                continue
            raw_path = str(item.get("path", "") or item.get("file", "") or "")
            if not raw_path:
                continue
            rel = _relative_path(raw_path, self.config.root_path)
            entry = {
                "path": rel,
                "score": float(item.get("score", item.get("similarity", 0.0)) or 0.0),
                "engine": "pinakes",
            }
            try:
                note = read_note(self.config.root_path, rel)
                entry["content"] = note.content[:3000]
                entry["metadata"] = note.metadata
            except (FileNotFoundError, ValueError):
                entry["content"] = ""
                entry["metadata"] = {}
            results.append(entry)
        return results[: self.config.max_search_results]

    def keyword_search(self, query: str, limit: int | None = None) -> list[dict]:
        limit = limit or self.config.max_search_results
        terms = [term for term in _tokenize(query) if len(term) >= 2]
        scored: list[dict] = []
        for rel in list_notes(self.config.root_path):
            try:
                note = read_note(self.config.root_path, rel)
            except (FileNotFoundError, ValueError):
                continue
            text = f"{rel}\n{note.content[:5000]}"
            score = 0.0
            for term in terms:
                count = text.count(term)
                if count:
                    score += 1.0 + count * 0.1
            if score > 0:
                scored.append(
                    {
                        "path": rel,
                        "score": round(score, 4),
                        "content": note.content[:3000],
                        "metadata": note.metadata,
                        "engine": "keyword",
                    }
                )
        scored.sort(key=lambda item: item["score"], reverse=True)
        return scored[:limit]


def _tokenize(text: str) -> list[str]:
    tokens: list[str] = []
    current = ""
    for char in text:
        if char.isalnum():
            current += char
        else:
            if current:
                tokens.append(current)
                current = ""
    if current:
        tokens.append(current)
    return tokens


def _relative_path(raw_path: str, root: Path) -> str:
    candidate = Path(raw_path).resolve()
    root_resolved = Path(root).resolve()
    try:
        return candidate.relative_to(root_resolved).as_posix()
    except ValueError:
        return Path(raw_path).name


def os_access(path: Path) -> bool:
    return path.is_file() and os.access(path, os.X_OK)
