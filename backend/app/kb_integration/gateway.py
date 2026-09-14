"""统一知识网关。

全局单例；负责知识库目录初始化、Markdown 读写、标签/目录检索、
Pinakes 语义检索（自动降级）以及标书上下文构建。
"""
from __future__ import annotations

import logging
import threading
import time
from pathlib import Path

from .config import KnowledgeBaseConfig
from .context_builder import ContextBuilder
from .file_handler import list_notes, read_note, safe_relative_path, write_note
from .pinakes_adapter import PinakesAdapter
from .tag_handler import list_tags, search_by_tag

logger = logging.getLogger(__name__)

_watcher_threads: dict[str, threading.Thread] = {}
_watcher_lock = threading.Lock()


class UnifiedKnowledgeGateway:
    def __init__(self, config: KnowledgeBaseConfig | None = None) -> None:
        self.config = config or KnowledgeBaseConfig.load()
        self.adapter = PinakesAdapter(self.config)
        self.context_builder = ContextBuilder(self.config, self.adapter)
        self._search_cache: dict = {}
        self._note_cache: dict = {}
        self._cache_lock = threading.Lock()
        self._initialized = False

    @property
    def root(self) -> Path:
        return Path(self.config.root_path)

    def initialize(self) -> dict:
        """首次启动：创建目录结构、示例笔记与 Pinakes 索引。"""
        started = time.monotonic()
        self.root.mkdir(parents=True, exist_ok=True)
        created = self._ensure_default_structure()
        index_status = "skipped"
        if self.adapter.available and not self.adapter.index_dir.exists():
            index_status = "ok" if self.adapter.init_index() else "failed"
        self._initialized = True
        self._start_watcher()
        notes_count = len(list_notes(self.root))
        logger.info(
            "[KNOWLEDGE] 初始化完成 | notes_count=%d | index_status=%s | duration=%.0fms",
            notes_count,
            index_status,
            (time.monotonic() - started) * 1000,
        )
        return {"created": created, "notes_count": notes_count, "index_status": index_status}

    def _start_watcher(self) -> None:
        """轻量文件监听：检测到知识库文件变更后刷新缓存并重建 Pinakes 索引。"""
        root_key = str(self.root.resolve())
        with _watcher_lock:
            if root_key in _watcher_threads:
                return
            thread = threading.Thread(target=self._watch_loop, args=(root_key,), daemon=True, name="kb-watcher")
            _watcher_threads[root_key] = thread
            thread.start()

    def _watch_loop(self, root_key: str) -> None:
        last = self._fingerprint()
        while True:
            time.sleep(10)
            try:
                current = self._fingerprint()
            except Exception:
                continue
            if current == last:
                continue
            logger.info("[KNOWLEDGE] 检测到知识库文件变更，刷新缓存并重建索引")
            with self._cache_lock:
                self._note_cache.clear()
                self._search_cache.clear()
            if self.adapter.available:
                self.adapter.reindex()
            last = current

    def _fingerprint(self) -> dict:
        fingerprint: dict[str, tuple[int, int]] = {}
        for rel in list_notes(self.root):
            target = self.root / rel
            try:
                stat = target.stat()
                fingerprint[rel] = (stat.st_mtime_ns, stat.st_size)
            except OSError:
                fingerprint[rel] = (0, 0)
        return fingerprint

    def _ensure_default_structure(self) -> list[str]:
        created: list[str] = []
        readme = self.root / "README.md"
        if not readme.exists():
            readme.write_text(_README_TEXT, encoding="utf-8")
            created.append("README.md")
        for key in (
            "qualifications",
            "historical_bids",
            "policies",
            "company_info",
            "templates",
            "product_docs",
            "system_generated",
        ):
            directory = self.config.dir(key)
            target = self.root / directory
            target.mkdir(parents=True, exist_ok=True)
            gitkeep = target / ".gitkeep"
            if not gitkeep.exists():
                gitkeep.write_text("", encoding="utf-8")
                created.append(f"{directory}/.gitkeep")
        sample = self.root / self.config.dir("qualifications") / "示例_营业执照.md"
        if not sample.exists():
            sample.write_text(_SAMPLE_NOTE, encoding="utf-8")
            created.append(f"{self.config.dir('qualifications')}/示例_营业执照.md")
        return created

    def read_note(self, rel_path: str) -> dict:
        rel = safe_relative_path(rel_path)
        with self._cache_lock:
            cached = self._note_cache.get(rel)
        if cached is not None:
            return cached
        note = read_note(self.root, rel)
        payload = {"path": note.path, "content": note.content, "metadata": note.metadata}
        with self._cache_lock:
            self._note_cache[rel] = payload
        return payload

    def write_note(self, rel_path: str, content: str, metadata: dict | None = None) -> dict:
        note = write_note(self.root, rel_path, content, metadata or {})
        payload = {"path": note.path, "content": note.content, "metadata": note.metadata}
        with self._cache_lock:
            self._note_cache[note.path] = payload
            self._search_cache.clear()
        if self.adapter.available:
            threading.Thread(target=self.adapter.reindex, daemon=True).start()
        return payload

    def list_notes(self, subdir: str = "", extension: str = ".md") -> list[str]:
        return list_notes(self.root, subdir=subdir, extension=extension)

    def search_by_tag(self, tag: str, subdir: str = "") -> list[str]:
        return search_by_tag(self.root, tag, subdir=subdir)

    def list_tags(self, subdir: str = "") -> dict[str, int]:
        return list_tags(self.root, subdir=subdir)

    def semantic_search(self, query: str, limit: int | None = None) -> dict:
        limit = limit or self.config.max_search_results
        cache_key = (query.strip(), limit)
        with self._cache_lock:
            cached = self._search_cache.get(cache_key)
        if cached is not None and time.monotonic() - cached["ts"] < 900:
            return cached["data"]
        results = self.adapter.semantic_search(query, limit=limit)
        engine = "pinakes" if results and results[0].get("engine") == "pinakes" else ("keyword" if results else "none")
        data = {"query": query, "engine": engine, "results": results}
        with self._cache_lock:
            self._search_cache[cache_key] = {"ts": time.monotonic(), "data": data}
        return data

    def get_context_for_bid(self, project_description: str = "", industry: str = "") -> dict:
        return self.context_builder.get_context_for_bid(project_description, industry)

    def status(self) -> dict:
        notes = list_notes(self.root)
        return {
            "root_path": str(self.root.resolve()),
            "config_path": str(Path(self.config.config_path).resolve()),
            "notes_count": len(notes),
            "pinakes_available": self.adapter.available,
            "pinakes_bin": str(Path(self.config.pinakes_bin).resolve()),
            "index_exists": self.adapter.index_dir.exists(),
            "fallback_on_error": self.config.fallback_on_error,
            "max_search_results": self.config.max_search_results,
            "search_timeout": self.config.search_timeout,
            "directories": dict(self.config.directories),
        }


_gateway: UnifiedKnowledgeGateway | None = None
_gateway_lock = threading.Lock()


def get_gateway() -> UnifiedKnowledgeGateway:
    global _gateway
    if _gateway is None:
        with _gateway_lock:
            if _gateway is None:
                _gateway = UnifiedKnowledgeGateway(KnowledgeBaseConfig.load())
    return _gateway


def reset_gateway(config: KnowledgeBaseConfig | None = None) -> UnifiedKnowledgeGateway:
    global _gateway
    with _gateway_lock:
        _gateway = UnifiedKnowledgeGateway(config or KnowledgeBaseConfig.load())
        return _gateway


_README_TEXT = """# 招投标知识库

本目录为 Obsidian 兼容知识库，使用 Markdown + Frontmatter 组织知识。

## 目录说明

- `01_企业资质/`：营业执照、认证证书、许可证等，系统检索资质时固定搜索
- `02_历史标书/`：历史项目标书，语义检索相似项目时优先搜索
- `03_行业政策/`：行业政策与招标规范，生成合规章节时参考
- `04_公司介绍/`：公司简介、核心团队等，生成公司介绍时读取
- `05_投标模板/`：按行业子目录存放标书模板，`通用/` 为回退目录
- `06_产品资料/`：产品手册、技术方案、检测报告等产品级素材
- `_system_generated/`：系统自动生成的内容

## 规范

- 建议在 Frontmatter 中维护 `tags`、`industry`、`valid_until` 等字段
- 正文支持 Obsidian `[[WikiLink]]` 与 `#标签` 语法
- 冲突文件（`*sync-conflict*`）会被系统自动忽略
"""

_SAMPLE_NOTE = """---
title: 示例-营业执照
tags:
  - 示例
  - 营业执照
industry: 通用
valid_until: 2028-12-31
---

# 示例笔记（可删除）

此文件为系统初始化生成的示例笔记。请将真实营业执照信息替换到本文件，
或直接删除本文件后在 Obsidian 中新建笔记。
"""
