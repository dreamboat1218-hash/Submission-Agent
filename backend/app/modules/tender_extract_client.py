"""tender-extract HTTP 服务适配器。"""
from __future__ import annotations

import logging
from pathlib import Path

import httpx

from ..config import get_settings

logger = logging.getLogger(__name__)


class TenderExtractUnavailable(RuntimeError):
    pass


class TenderExtractClient:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.base_url = self.settings.tender_extract_url.rstrip("/")
        self.timeout = self.settings.tender_extract_timeout

    def health(self) -> dict:
        try:
            response = httpx.get(f"{self.base_url}/healthz", timeout=3)
            response.raise_for_status()
            return response.json()
        except Exception as exc:
            raise TenderExtractUnavailable(f"tender-extract 服务不可达：{exc}") from exc

    def extract_file(self, path: str | Path, mode: str = "fast", llm_provider: str | None = None) -> dict:
        headers = {}
        if self.settings.tender_extract_api_key:
            headers["X-API-Key"] = self.settings.tender_extract_api_key
        params = {"confidence_threshold": 0.7}
        if mode == "precise":
            provider = llm_provider or self.settings.tender_llm_provider or self.settings.llm_provider
            params["llm_provider"] = provider
            model = self.settings.tender_llm_model
            if not model:
                if provider == "deepseek":
                    model = self.settings.deepseek_model
                elif provider == "openai":
                    model = self.settings.openai_model
            if model:
                params["llm_model"] = model

        with open(path, "rb") as fp:
            try:
                response = httpx.post(
                    f"{self.base_url}/v1/extract",
                    params=params,
                    files={"file": (Path(path).name, fp)},
                    headers=headers,
                    timeout=self.timeout,
                )
                response.raise_for_status()
            except Exception as exc:
                raise TenderExtractUnavailable(f"tender-extract 抽取失败：{exc}") from exc
        return response.json()

    @staticmethod
    def map_fields(raw: dict) -> dict[str, dict]:
        """将 tender-extract 字段名映射到需求文档的 26 字段。"""
        fields = raw.get("result", {}).get("fields", raw.get("fields", {}))
        mapping = {
            "project_name": "project_name",
            "project_number": "bid_number",
            "bid_number": "bid_number",
            "bid_amount": "budget",
            "bid_date": "bid_deadline",
            "deposit": "bid_security_amount",
            "tenderer": "tenderer",
            "contact_info": "contact_phone",
            "qualification_cert": "qualifications",
        }
        mapped: dict[str, dict] = {}
        for source_field, target_field in mapping.items():
            item = fields.get(source_field)
            if not item:
                continue
            evidence = {}
            values = item.get("values") or []
            if values:
                location = values[0].get("location") or {}
                evidence = {
                    "source_file": location.get("document_id", ""),
                    "page": location.get("page") or 1,
                    "text": values[0].get("ref") or location.get("source_text") or "",
                }
            mapped[target_field] = {
                "primary_value": item.get("primary_value"),
                "confidence": item.get("confidence", 0.5),
                "evidence": evidence,
            }
        return mapped
