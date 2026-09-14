"""章节知识映射规则的读写存储。

规则优先从 data/kb_chapter_rules.json 读取（Web 页面可维护），
未配置时回退到 config.yaml 的 knowledge_base.chapter_rules，最后使用内置默认规则。
"""
from __future__ import annotations

import copy
import json
import logging
import threading
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)


DEFAULT_CHAPTER_RULES = [
    {
        "keywords": ["公司简介", "公司介绍", "企业介绍", "单位简介"],
        "directories": ["04_公司介绍"],
        "tags": [],
        "query": "公司简介 主营业务 核心能力 团队 资质",
        "max_items": 3,
    },
    {
        "keywords": ["资质证明", "企业资质", "资质响应", "资格文件", "资质材料"],
        "directories": ["01_企业资质"],
        "tags": ["资质", "证书", "认证", "营业执照", "许可证"],
        "query": "营业执照 ISO 认证 资质 许可证",
        "max_items": 5,
    },
    {
        "keywords": ["技术方案", "技术文件", "总体方案", "技术需求响应", "技术响应"],
        "directories": ["02_历史标书"],
        "tags": ["技术方案", "成功案例", "中标"],
        "query": "技术方案 系统 设备 实施 部署",
        "max_items": 3,
    },
    {
        "keywords": ["销售业绩", "类似项目业绩", "项目业绩", "业绩文件"],
        "directories": ["02_历史标书"],
        "tags": ["业绩", "案例"],
        "query": "项目业绩 合同 验收 供货",
        "max_items": 4,
    },
    {
        "keywords": ["售后服务", "质量承诺", "质量保证", "培训"],
        "directories": ["04_公司介绍"],
        "tags": ["售后", "服务"],
        "query": "售后服务 质量承诺 保修 培训 支持",
        "max_items": 3,
    },
    {
        "keywords": ["合规", "政策", "响应性说明", "格式符合性"],
        "directories": ["03_行业政策"],
        "tags": ["政策", "规范"],
        "query": "政策 规范 合规 标准",
        "max_items": 3,
    },
    {
        "keywords": ["投标文件格式", "投标模板", "格式模板"],
        "directories": ["05_投标模板"],
        "tags": [],
        "query": "投标文件格式 模板",
        "max_items": 2,
    },
]


_BACKEND_ROOT = Path(__file__).resolve().parent.parent.parent
_rules_path = _BACKEND_ROOT / "data" / "kb_chapter_rules.json"
_cache: list[dict] | None = None
_lock = threading.Lock()


def _load_from_config() -> list[dict]:
    config_path = _BACKEND_ROOT / "config.yaml"
    if config_path.exists():
        try:
            raw = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
            section = raw.get("knowledge_base", {}).get("chapter_rules")
            if isinstance(section, list) and section:
                return [dict(rule) for rule in section if isinstance(rule, dict)]
        except Exception:
            pass
    return [dict(rule) for rule in DEFAULT_CHAPTER_RULES]


def get_chapter_rules() -> list[dict]:
    global _cache
    with _lock:
        if _cache is not None:
            return copy.deepcopy(_cache)
        if _rules_path.exists():
            try:
                data = json.loads(_rules_path.read_text(encoding="utf-8"))
                rules = data.get("rules", []) if isinstance(data, dict) else []
                if rules:
                    _cache = [dict(rule) for rule in rules]
                    return copy.deepcopy(_cache)
            except Exception as exc:
                logger.warning("章节规则 JSON 读取失败：%s", exc)
        _cache = _load_from_config()
        return copy.deepcopy(_cache)


def save_chapter_rules(rules: list[dict]) -> list[dict]:
    global _cache
    cleaned: list[dict] = []
    for rule in rules:
        if not isinstance(rule, dict):
            continue
        cleaned.append(
            {
                "keywords": [str(item).strip() for item in rule.get("keywords", []) if str(item).strip()],
                "directories": [str(item).strip() for item in rule.get("directories", []) if str(item).strip()],
                "tags": [str(item).strip() for item in rule.get("tags", []) if str(item).strip()],
                "frontmatter": [str(item).strip() for item in rule.get("frontmatter", []) if str(item).strip()],
                "query": str(rule.get("query", "") or "").strip(),
                "max_items": max(1, min(int(rule.get("max_items", 3) or 3), 20)),
            }
        )
    _rules_path.parent.mkdir(parents=True, exist_ok=True)
    _rules_path.write_text(json.dumps({"version": 1, "rules": cleaned}, ensure_ascii=False, indent=2), encoding="utf-8")
    with _lock:
        _cache = copy.deepcopy(cleaned)
    return copy.deepcopy(cleaned)
