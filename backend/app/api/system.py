from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends

from .. import __version__
from ..config import get_settings
from ..modules.tender_extract_client import TenderExtractClient, TenderExtractUnavailable
from ..schemas import HealthResponse, SettingsOut, SettingsUpdateIn
from ..security import get_current_user

router = APIRouter(tags=["系统"])
_ENV_PATH = Path(__file__).resolve().parent.parent.parent / ".env"
_TENDER_REPO_PATH = Path("/Users/supeng/Desktop/投标助手2/tender-extract-main")
_TENDER_LLM_ENV_BY_PROVIDER = {
    "siliconflow": "SILICONFLOW_API_KEY",
    "deepseek": "DEEPSEEK_API_KEY",
    "openai": "OPENAI_API_KEY",
    "qwen": "DASHSCOPE_API_KEY",
    "dashscope": "DASHSCOPE_API_KEY",
    "moonshot": "MOONSHOT_API_KEY",
    "kimi": "MOONSHOT_API_KEY",
    "zhipu": "ZHIPUAI_API_KEY",
    "glm": "ZHIPUAI_API_KEY",
    "doubao": "ARK_API_KEY",
    "volcengine": "ARK_API_KEY",
    "hunyuan": "HUNYUAN_API_KEY",
    "baichuan": "BAICHUAN_API_KEY",
    "minimax": "MINIMAX_API_KEY",
    "stepfun": "STEPFUN_API_KEY",
    "openrouter": "OPENROUTER_API_KEY",
    "groq": "GROQ_API_KEY",
    "together": "TOGETHER_API_KEY",
    "mistral": "MISTRAL_API_KEY",
    "xai": "XAI_API_KEY",
    "grok": "XAI_API_KEY",
    "fireworks": "FIREWORKS_API_KEY",
    "perplexity": "PERPLEXITY_API_KEY",
    "openai_compat": "LLM_API_KEY",
}


def _mask_secret(value: str) -> str:
    return "******" if value else ""


def _provider_configs(settings) -> list[dict]:
    if settings.tender_llm_providers_json:
        try:
            data = json.loads(settings.tender_llm_providers_json)
            if isinstance(data, list):
                return [dict(item) for item in data if isinstance(item, dict)]
        except json.JSONDecodeError:
            pass
    if settings.tender_llm_provider and settings.tender_llm_provider != "none":
        return [
            {
                "provider": settings.tender_llm_provider,
                "model": settings.tender_llm_model,
                "api_key": settings.tender_llm_api_key,
                "base_url": settings.tender_llm_base_url,
            }
        ]
    return []


def _providers_out(settings) -> list[dict]:
    return [
        {
            "provider": item.get("provider", ""),
            "model": item.get("model", ""),
            "api_key": _mask_secret(item.get("api_key", "") or ""),
            "base_url": item.get("base_url", ""),
        }
        for item in _provider_configs(settings)
    ]


def _update_env_file(updates: dict[str, str]) -> None:
    lines = _ENV_PATH.read_text(encoding="utf-8").splitlines() if _ENV_PATH.exists() else []
    updated: list[str] = []
    seen: set[str] = set()
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            updated.append(line)
            continue
        key = stripped.split("=", 1)[0].strip()
        if key in updates:
            updated.append(f"{key}={updates[key]}")
            seen.add(key)
        else:
            updated.append(line)
    for key, value in updates.items():
        if key not in seen:
            updated.append(f"{key}={value}")
    _ENV_PATH.parent.mkdir(parents=True, exist_ok=True)
    _ENV_PATH.write_text("\n".join(updated) + "\n", encoding="utf-8")


def _write_tender_server_env(settings) -> None:
    """把 LLM 配置同步到 tender-extract 服务启动时读取的 env 文件。"""
    if not _TENDER_REPO_PATH.exists():
        return
    providers = _provider_configs(settings)
    values: dict[str, str] = {
        "TENDER_SERVER_LLM_PROVIDER": providers[0]["provider"] if providers else "none",
        "TENDER_SERVER_LLM_MODEL": providers[0]["model"] if providers else "",
        "TENDER_SERVER_USE_OCR": "true",
    }
    if providers:
        values["TENDER_SERVER_LLM_PROVIDERS_JSON"] = json.dumps(providers, ensure_ascii=False)
    for item in providers:
        provider = str(item.get("provider", "")).lower()
        api_key = str(item.get("api_key", "") or "")
        if api_key:
            values[_TENDER_LLM_ENV_BY_PROVIDER.get(provider, "LLM_API_KEY")] = api_key
        base_url = str(item.get("base_url", "") or "")
        if base_url:
            values["LLM_BASE_URL"] = base_url
    env_path = _TENDER_REPO_PATH / ".tender-server.env"
    env_path.write_text(
        "\n".join(f"{key}={value}" for key, value in values.items() if value is not None) + "\n",
        encoding="utf-8",
    )


@router.get("/health/live")
def health_live() -> dict:
    """轻量存活探针：不做任何外部服务探测，供桌面端启动检查使用。"""
    return {"status": "ok", "version": __version__}


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    settings = get_settings()
    services = {"api": "ok"}
    try:
        services["tender_extract"] = "ok" if TenderExtractClient().health().get("status") == "ok" else "unknown"
    except TenderExtractUnavailable:
        services["tender_extract"] = "unavailable (using fallback)"
    if settings.biaoshu_skill_path:
        services["biaoshu"] = "configured" if Path(settings.biaoshu_skill_path).exists() else "missing"
    else:
        services["biaoshu"] = "not configured (using builtin generator)"
    return HealthResponse(status="ok", version=__version__, services=services)


@router.get("/settings", response_model=SettingsOut)
def settings_view(user=Depends(get_current_user)) -> SettingsOut:
    settings = get_settings()
    return SettingsOut(
        app_name=settings.app_name,
        system_env=settings.system_env,
        llm_provider=settings.llm_provider,
        tender_extract_url=settings.tender_extract_url,
        tender_extract_api_key=_mask_secret(settings.tender_extract_api_key),
        tender_llm_provider=settings.tender_llm_provider,
        tender_llm_model=settings.tender_llm_model,
        tender_llm_api_key=_mask_secret(settings.tender_llm_api_key),
        tender_llm_base_url=settings.tender_llm_base_url,
        tender_llm_providers=_providers_out(settings),
        biaoshu_skill_path=settings.biaoshu_skill_path,
        use_vector_search=settings.use_vector_search,
        max_file_size=settings.max_file_size,
        max_extract_depth=settings.max_extract_depth,
        max_files_per_task=settings.max_files_per_task,
    )


@router.put("/settings", response_model=SettingsOut)
def update_settings(payload: SettingsUpdateIn, user=Depends(get_current_user)) -> SettingsOut:
    settings = get_settings()
    updates: dict[str, str] = {}
    if payload.tender_extract_url is not None:
        updates["TENDER_EXTRACT_URL"] = payload.tender_extract_url.strip()
    if payload.tender_extract_api_key is not None:
        if payload.tender_extract_api_key.strip() != "******":
            updates["TENDER_EXTRACT_API_KEY"] = payload.tender_extract_api_key.strip()
    if payload.tender_llm_provider is not None:
        updates["TENDER_LLM_PROVIDER"] = payload.tender_llm_provider.strip() or "none"
    if payload.tender_llm_model is not None:
        updates["TENDER_LLM_MODEL"] = payload.tender_llm_model.strip()
    if payload.tender_llm_api_key is not None:
        if payload.tender_llm_api_key.strip() != "******":
            updates["TENDER_LLM_API_KEY"] = payload.tender_llm_api_key.strip()
    if payload.tender_llm_base_url is not None:
        updates["TENDER_LLM_BASE_URL"] = payload.tender_llm_base_url.strip()
    if payload.tender_llm_providers is not None:
        existing = _provider_configs(settings)
        cleaned: list[dict] = []
        for index, item in enumerate(payload.tender_llm_providers):
            provider = str(item.get("provider", "") or "").strip()
            api_key = str(item.get("api_key", "") or "")
            if api_key == "******" and index < len(existing):
                api_key = str(existing[index].get("api_key", "") or "")
            cleaned.append(
                {
                    "provider": provider,
                    "model": str(item.get("model", "") or "").strip(),
                    "api_key": api_key.strip(),
                    "base_url": str(item.get("base_url", "") or "").strip(),
                }
            )
        updates["TENDER_LLM_PROVIDERS_JSON"] = json.dumps(cleaned, ensure_ascii=False)
        if cleaned:
            first = cleaned[0]
            updates["TENDER_LLM_PROVIDER"] = first["provider"]
            updates["TENDER_LLM_MODEL"] = first["model"]
            updates["TENDER_LLM_API_KEY"] = first["api_key"]
            updates["TENDER_LLM_BASE_URL"] = first["base_url"]
        else:
            updates["TENDER_LLM_PROVIDER"] = "none"
            updates["TENDER_LLM_MODEL"] = ""
            updates["TENDER_LLM_API_KEY"] = ""
            updates["TENDER_LLM_BASE_URL"] = ""
    if payload.biaoshu_skill_path is not None:
        updates["BIAOSHU_SKILL_PATH"] = payload.biaoshu_skill_path.strip()
    if updates:
        _update_env_file(updates)
        get_settings.cache_clear()
    settings = get_settings()
    _write_tender_server_env(settings)
    return SettingsOut(
        app_name=settings.app_name,
        system_env=settings.system_env,
        llm_provider=settings.llm_provider,
        tender_extract_url=settings.tender_extract_url,
        tender_extract_api_key=_mask_secret(settings.tender_extract_api_key),
        tender_llm_provider=settings.tender_llm_provider,
        tender_llm_model=settings.tender_llm_model,
        tender_llm_api_key=_mask_secret(settings.tender_llm_api_key),
        tender_llm_base_url=settings.tender_llm_base_url,
        tender_llm_providers=_providers_out(settings),
        biaoshu_skill_path=settings.biaoshu_skill_path,
        use_vector_search=settings.use_vector_search,
        max_file_size=settings.max_file_size,
        max_extract_depth=settings.max_extract_depth,
        max_files_per_task=settings.max_files_per_task,
    )
