"""系统配置。

所有配置均可通过环境变量覆盖，环境变量名与字段名保持大小写不敏感一致，
例如 ``BID_SYSTEM_ENV``、``DATABASE_URL``、``TENDER_EXTRACT_URL``。
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "招投标智能体集成系统"
    system_env: str = "development"
    debug: bool = False
    secret_key: str = "change-me-in-production"
    jwt_expire_hours: int = 24
    rate_limit_requests: int = 100
    rate_limit_period: int = 60
    disable_auth: bool = False

    database_url: str = "sqlite:///./bid_agent.db"
    redis_url: str = "redis://localhost:6379/0"

    data_dir: str = "./data"
    temp_dir: str = "./data/tmp"
    generated_dir: str = "./data/generated"
    max_file_size: int = 524288000
    max_extract_depth: int = 10
    max_files_per_task: int = 50
    file_cleanup_hours: int = 24

    tender_extract_url: str = "http://localhost:8000"
    tender_extract_timeout: int = 60
    tender_extract_api_key: str = ""
    tender_llm_provider: str = "none"
    tender_llm_model: str = ""
    tender_llm_api_key: str = ""
    tender_llm_base_url: str = ""
    tender_llm_providers_json: str = ""

    llm_provider: str = "none"
    deepseek_api_key: str = ""
    deepseek_model: str = "deepseek-chat"
    deepseek_base_url: str = "https://api.deepseek.com/v1"
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    openai_base_url: str = "https://api.openai.com/v1"
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "qwen2.5:7b"

    knowledge_base_path: str = "./data/kb"
    chroma_persist_dir: str = "./data/chroma_db"
    embedding_model: str = "BAAI/bge-large-zh-v1.5"
    use_vector_search: bool = False

    biaoshu_skill_path: str = ""
    biaoshu_output_dir: str = "./data/generated"
    biaoshu_timeout: int = 300

    cors_origins: str = "*"

    @property
    def data_path(self) -> Path:
        return Path(self.data_dir)

    @property
    def tasks_dir(self) -> Path:
        return self.data_path / "tasks"

    @property
    def kb_path(self) -> Path:
        return Path(self.knowledge_base_path)

    def ensure_dirs(self) -> None:
        for path in (self.tasks_dir, Path(self.temp_dir), Path(self.generated_dir), self.kb_path, Path(self.chroma_persist_dir)):
            path.mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    return Settings()
