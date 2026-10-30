"""国网投标专用章节知识映射规则。

规则独立于通用章节知识映射，优先从 data/bid_chapter_rules.json 读取；
未保存时使用固定默认规则，可在前端“国网投标专项 -> 知识映射规则”中维护。
"""
from __future__ import annotations

import copy
import json
import logging
import os
import threading
from pathlib import Path

logger = logging.getLogger(__name__)


DEFAULT_BID_CHAPTER_RULES = [
    {
        "keywords": ["资质业绩凭证单", "资格文件", "资质要求", "其它资质要求"],
        "directories": ["共享/01_企业资质", "01_企业资质"],
        "tags": ["资质", "凭证"],
        "frontmatter": ["doc_type:企业资质"],
        "query": "资质业绩凭证单 营业执照 资质要求",
        "max_items": 4,
    },
    {
        "keywords": ["公司简介", "公司介绍", "单位简介"],
        "directories": ["共享/04_公司介绍", "04_公司介绍"],
        "tags": ["公司简介"],
        "frontmatter": ["doc_type:公司介绍"],
        "query": "公司简介 主营业务 核心能力 团队",
        "max_items": 2,
    },
    {
        "keywords": ["投标人类别", "人力资源"],
        "directories": ["共享/04_公司介绍", "04_公司介绍"],
        "tags": ["人力资源"],
        "frontmatter": ["doc_type:公司介绍"],
        "query": "投标人类别 制造商 代理商 人力资源 职称",
        "max_items": 3,
    },
    {
        "keywords": ["销售业绩", "项目业绩", "类似项目业绩", "业绩文件"],
        "directories": ["国网专属/02_历史标书", "02_历史标书"],
        "tags": ["业绩", "中标"],
        "frontmatter": ["status:已中标"],
        "query": "类似项目业绩 合同 验收 供货",
        "max_items": 5,
    },
    {
        "keywords": ["检测（试验）报告", "检测报告", "试验报告"],
        "directories": ["国网专属/06_产品资料", "06_产品资料"],
        "tags": ["检测报告"],
        "frontmatter": ["doc_type:检测报告"],
        "query": "型式试验 检测报告 产品型号",
        "max_items": 5,
    },
    {
        "keywords": ["认证证书", "认证"],
        "directories": ["共享/01_企业资质", "01_企业资质"],
        "tags": ["认证证书"],
        "frontmatter": ["doc_type:认证证书"],
        "query": "ISO CCC 认证证书",
        "max_items": 5,
    },
    {
        "keywords": ["许可证"],
        "directories": ["共享/01_企业资质", "01_企业资质"],
        "tags": ["许可证"],
        "frontmatter": ["doc_type:许可证"],
        "query": "生产许可证 入网许可证",
        "max_items": 3,
    },
    {
        "keywords": ["生产设备"],
        "directories": ["共享/01_企业资质", "01_企业资质"],
        "tags": ["生产设备"],
        "frontmatter": ["doc_type:生产设备"],
        "query": "生产设备 工装 生产能力",
        "max_items": 5,
    },
    {
        "keywords": ["试验设备"],
        "directories": ["共享/01_企业资质", "01_企业资质"],
        "tags": ["试验设备"],
        "frontmatter": ["doc_type:试验设备"],
        "query": "试验设备 检定 试验能力",
        "max_items": 5,
    },
    {
        "keywords": ["厂房环境", "厂房"],
        "directories": ["共享/01_企业资质", "01_企业资质"],
        "tags": ["厂房"],
        "frontmatter": ["doc_type:厂房环境"],
        "query": "厂房 面积 净化车间",
        "max_items": 3,
    },
    {
        "keywords": ["售后服务", "质量承诺", "技术支持"],
        "directories": ["共享/04_公司介绍", "04_公司介绍"],
        "tags": ["售后"],
        "frontmatter": ["doc_type:售后服务"],
        "query": "售后服务 质保 响应 培训",
        "max_items": 3,
    },
    {
        "keywords": ["技术方案", "应答文件", "组件材料", "其它技术内容"],
        "directories": ["国网专属/06_产品资料", "06_产品资料"],
        "tags": ["技术方案"],
        "frontmatter": ["doc_type:技术方案"],
        "query": "产品技术方案 实施 部署",
        "max_items": 3,
    },
    {
        "keywords": ["政策", "合规", "响应性说明"],
        "directories": ["国网专属/03_行业政策", "03_行业政策"],
        "tags": ["政策"],
        "frontmatter": ["doc_type:行业政策"],
        "query": "政策 规范 标准",
        "max_items": 3,
    },
]


def _data_root() -> Path:
    """桌面端使用 DATA_DIR（用户目录），源码调试时回落到 backend/data。"""
    configured = os.getenv("DATA_DIR", "").strip()
    if configured:
        return Path(configured)
    return Path(__file__).resolve().parent.parent.parent / "data"


_rules_path = _data_root() / "bid_chapter_rules.json"
_cache: list[dict] | None = None
_lock = threading.Lock()


def _clone_defaults() -> list[dict]:
    return copy.deepcopy(DEFAULT_BID_CHAPTER_RULES)


def get_bid_chapter_rules() -> list[dict]:
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
                logger.warning("国网投标规则 JSON 读取失败：%s", exc)
        _cache = _clone_defaults()
        return copy.deepcopy(_cache)


def save_bid_chapter_rules(rules: list[dict]) -> list[dict]:
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
    _rules_path.write_text(
        json.dumps({"version": 1, "scope": "bid_special", "rules": cleaned}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    with _lock:
        _cache = copy.deepcopy(cleaned)
    return copy.deepcopy(cleaned)


def reset_bid_chapter_rules() -> list[dict]:
    return save_bid_chapter_rules(_clone_defaults())
