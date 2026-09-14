"""知识网关配置。

优先读取项目根目录 config.yaml 的 ``knowledge_base`` 段，其次使用环境变量
覆盖（KNOWLEDGE_BASE_ROOT、PINAKES_BIN 等），最后使用默认值。
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml


_BACKEND_ROOT = Path(__file__).resolve().parent.parent.parent


DEFAULT_DIRECTORIES = {
    "qualifications": "01_企业资质",
    "historical_bids": "02_历史标书",
    "policies": "03_行业政策",
    "company_info": "04_公司介绍",
    "templates": "05_投标模板",
    "product_docs": "06_产品资料",
    "system_generated": "_system_generated",
}


@dataclass
class KnowledgeBaseConfig:
    root_path: Path = field(
        default_factory=lambda: Path(os.getenv("KNOWLEDGE_BASE_ROOT", str(_BACKEND_ROOT / "knowledge_base")))
    )
    pinakes_bin: Path = field(
        default_factory=lambda: Path(os.getenv("PINAKES_BIN", str(_BACKEND_ROOT / "bin" / "pinakes")))
    )
    max_search_results: int = 5
    search_timeout: float = 15.0
    fallback_on_error: bool = True
    directories: dict = field(default_factory=lambda: dict(DEFAULT_DIRECTORIES))
    config_path: Path = field(
        default_factory=lambda: Path(os.getenv("KNOWLEDGE_CONFIG", str(_BACKEND_ROOT / "config.yaml")))
    )

    @classmethod
    def load(cls, config_path: Path | None = None) -> "KnowledgeBaseConfig":
        config = cls()
        path = config_path or config.config_path
        if path and Path(path).exists():
            try:
                raw = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
                section = raw.get("knowledge_base", raw) or {}
                config = cls._from_section(section)
                base = Path(path).resolve().parent
                if not config.root_path.is_absolute():
                    config.root_path = (base / config.root_path).resolve()
                if not config.pinakes_bin.is_absolute():
                    config.pinakes_bin = (base / config.pinakes_bin).resolve()
                config.config_path = Path(path).resolve()
            except Exception:
                config = cls()
        return config

    @classmethod
    def _from_section(cls, section: dict) -> "KnowledgeBaseConfig":
        directories = dict(DEFAULT_DIRECTORIES)
        raw_dirs = section.get("directories") or {}
        if isinstance(raw_dirs, dict):
            directories.update({str(k): str(v) for k, v in raw_dirs.items() if v})
        config = cls(
            root_path=Path(str(section.get("root_path", "./knowledge_base"))),
            pinakes_bin=Path(str(section.get("pinakes_bin", "./bin/pinakes"))),
            max_search_results=int(section.get("max_search_results", 5)),
            search_timeout=float(section.get("search_timeout", 15.0)),
            fallback_on_error=bool(section.get("fallback_on_error", True)),
            directories=directories,
        )
        for key, value in (
            ("KNOWLEDGE_BASE_ROOT", "root_path"),
            ("PINAKES_BIN", "pinakes_bin"),
        ):
            env_value = os.getenv(key)
            if env_value:
                setattr(config, value, Path(env_value))
        return config

    def dir(self, key: str) -> str:
        return str(self.directories.get(key, DEFAULT_DIRECTORIES.get(key, key)))
