"""模块二：信息抽取。

优先调用 tender-extract HTTP 服务；服务不可用时降级到内置规则引擎；
精准模式下若配置了 LLM，会对低置信字段进行复核。
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Callable

from sqlalchemy.orm import Session

from ..config import get_settings
from ..database import get_session_factory
from ..models import Task
from . import fallback_extractor
from .reference_resolver import enrich_missing_fields, resolve_references
from .tender_extract_client import TenderExtractClient, TenderExtractUnavailable

logger = logging.getLogger(__name__)

ProgressCallback = Callable[[float, str], None]


def run(task_id: str, mode: str = "fast", progress_cb: ProgressCallback | None = None) -> dict:
    settings = get_settings()
    factory = get_session_factory()
    with factory() as db:
        task = db.get(Task, task_id)
        if task is None:
            raise ValueError(f"task not found: {task_id}")
        manifest = task.manifest or {}

    md_entries = [entry for entry in manifest.get("files", []) if entry.get("status") == "converted" and entry.get("md_path")]
    md_files = [Path(entry["md_path"]) for entry in md_entries]
    if not md_files:
        raise RuntimeError("没有可抽取的 Markdown 文档")

    provider = "fallback-rules"
    if progress_cb:
        progress_cb(0.05, "检查 tender-extract 服务")
    try:
        client = TenderExtractClient()
        client.health()
        results: list[dict] = []
        for index, (md_path, entry) in enumerate(zip(md_files, md_entries)):
            raw = client.extract_file(md_path, mode=mode)
            results.append(TenderExtractClient.map_fields(raw))
            if progress_cb:
                progress_cb(0.1 + 0.45 * (index + 1) / len(md_files), f"tender-extract 处理 {md_path.name}")
        provider = "tender-extract"
    except TenderExtractUnavailable as exc:
        logger.warning("tender-extract 不可用，降级到规则引擎：%s", exc)
        if progress_cb:
            progress_cb(0.1, "tender-extract 不可用，使用内置规则引擎")
        results = []
        for index, (md_path, entry) in enumerate(zip(md_files, md_entries)):
            content = md_path.read_text(encoding="utf-8", errors="replace")
            results.append(fallback_extractor.extract_file(content, md_path.name))
            if progress_cb:
                progress_cb(0.1 + 0.45 * (index + 1) / len(md_files), f"规则抽取 {md_path.name}")

    for result, entry in zip(results, md_entries):
        fmt = result.get("bid_format")
        if fmt and isinstance(fmt.get("primary_value"), dict):
            fmt["primary_value"]["source_path"] = entry.get("path", "")

    data = fallback_extractor.merge(results)
    llm_calls = 0
    if mode == "precise" and settings.llm_provider != "none":
        if progress_cb:
            progress_cb(0.6, "LLM 复核低置信字段")
        refined, llm_calls = _refine_with_llm(task_id, data, mode)
        data = refined

    data = enrich_missing_fields(task_id, data)
    data = resolve_references(task_id, data)
    combined_text = "\n".join(md.read_text(encoding="utf-8", errors="replace") for md in md_files)
    data["_meta"] = {
        "mode": mode,
        "provider": provider,
        "source_files": [md.name for md in md_files],
        "confidence_summary": fallback_extractor.summarize(data),
        "llm_calls": llm_calls,
        "field_count": sum(1 for f in fallback_extractor.FIELD_LABELS if data.get(f)),
    }
    if progress_cb:
        summary = data["_meta"]["confidence_summary"]
        progress_cb(0.75, f"抽取完成：高置信 {summary['high']}，中置信 {summary['medium']}，低置信 {summary['low']}")
    return data


def data_to_text(data: dict) -> str:
    parts = []
    for field in fallback_extractor.FIELD_LABELS:
        item = data.get(field)
        if item:
            value = item.get("primary_value")
            if isinstance(value, list):
                parts.append(" ".join(str(v) for v in value))
            elif value is not None:
                parts.append(str(value))
    fmt = data.get("bid_format", {})
    if isinstance(fmt, dict) and isinstance(fmt.get("primary_value"), dict):
        raw = fmt["primary_value"].get("raw", "")
        if raw:
            parts.append(str(raw))
    return "\n".join(parts)


def _refine_with_llm(task_id: str, data: dict, mode: str) -> tuple[dict, int]:
    settings = get_settings()
    if settings.llm_provider not in {"deepseek", "openai", "ollama"}:
        return data, 0
    with get_session_factory()() as db:
        task = db.get(Task, task_id)
        combined_path = Path(task.work_dir) / "combined.md"
        document = combined_path.read_text(encoding="utf-8", errors="replace")[:30000] if combined_path.exists() else ""

    schema = {
        field: {"type": "string|number|list", "description": label}
        for field, label in fallback_extractor.FIELD_LABELS.items()
    }
    existing = {k: v.get("primary_value") for k, v in data.items()}
    prompt = (
        "你是招投标信息抽取专家。请根据招标文件原文，抽取以下26个字段：\n"
        f"{json.dumps(schema, ensure_ascii=False, indent=2)}\n\n"
        "只输出JSON对象，字段名固定，值为字符串、数字或字符串数组；"
        "原文中没有的字段不要输出。不要输出任何解释。\n\n"
        f"已有规则抽取结果（可校正，不要凭空编造）：\n{json.dumps(existing, ensure_ascii=False)}\n\n"
        f"招标文件原文（截断）：\n{document}"
    )
    try:
        response = _chat_completion(prompt)
        parsed = json.loads(response)
        if not isinstance(parsed, dict):
            return data, 1
        for field in fallback_extractor.FIELD_LABELS:
            if field in parsed and parsed[field] not in (None, "", [], {}):
                old = data.get(field, {})
                data[field] = {
                    "primary_value": parsed[field],
                    "confidence": max(float(old.get("confidence", 0)), 0.75),
                    "evidence": old.get("evidence", {"source_file": "", "page": 1, "text": "LLM 复核结果"}),
                }
        return data, 1
    except Exception as exc:
        logger.warning("LLM 复核失败，保留规则结果：%s", exc)
        return data, 0


def _chat_completion(prompt: str) -> str:
    settings = get_settings()
    if settings.llm_provider == "deepseek":
        url = f"{settings.deepseek_base_url.rstrip('/')}/chat/completions"
        key = settings.deepseek_api_key
        model = settings.deepseek_model
    elif settings.llm_provider == "openai":
        url = f"{settings.openai_base_url.rstrip('/')}/chat/completions"
        key = settings.openai_api_key
        model = settings.openai_model
    else:
        url = f"{settings.ollama_base_url.rstrip('/')}/v1/chat/completions"
        key = ""
        model = settings.ollama_model

    headers = {"Content-Type": "application/json"}
    if key:
        headers["Authorization"] = f"Bearer {key}"
    import httpx

    response = httpx.post(
        url,
        headers=headers,
        json={
            "model": model,
            "messages": [{"role": "system", "content": "你是严谨的招投标文档信息抽取助手。"}, {"role": "user", "content": prompt}],
            "temperature": 0.1,
            "response_format": {"type": "json_object"},
        },
        timeout=120,
    )
    response.raise_for_status()
    return response.json()["choices"][0]["message"]["content"]
