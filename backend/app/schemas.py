from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    username: str
    password: str


class UserOut(BaseModel):
    id: str
    username: str
    role: str


class TokenResponse(BaseModel):
    token: str
    user: UserOut


class RunRequest(BaseModel):
    mode: str = Field("fast", pattern="^(fast|precise)$")
    industry: str = "auto"
    use_kb: bool = True
    with_check: bool = True


class ExtractRequest(BaseModel):
    task_id: str
    mode: str = Field("fast", pattern="^(fast|precise)$")


class GenerateRequest(BaseModel):
    task_id: str
    industry: str = "auto"
    use_kb: bool = True


class CheckRequest(BaseModel):
    task_id: str


class GeneratePackageBidRequest(BaseModel):
    files: list[str] = Field(default_factory=list, description="勾选的技术规范书 md_path 列表")
    subproject: str | None = Field(default=None, description="分标目录名或分标名称，用于区分同名包号")


class TaskOut(BaseModel):
    id: str
    user_id: str
    status: str
    current_stage: str
    progress: float
    message: str
    original_file_name: str
    file_count: int
    manifest: dict | None
    extracted_data: dict | None
    industry: str
    bid_file_path: str
    check_result: dict | None
    mode: str
    source: str = "workbench"
    error_message: str
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None


class TaskListResponse(BaseModel):
    total: int
    items: list[TaskOut]


class KbDocumentIn(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    content: str = ""
    doc_type: str = "企业资质"
    metadata: dict[str, Any] = Field(default_factory=dict)
    file_path: str = ""
    directory: str | None = Field(default=None, description="Obsidian 知识库目录，如 01_企业资质")
    tags: list[str] = Field(default_factory=list, description="Obsidian 笔记标签")


class KbDocumentUpdate(BaseModel):
    title: str | None = None
    content: str | None = None
    doc_type: str | None = None
    metadata: dict[str, Any] | None = None
    directory: str | None = None
    tags: list[str] | None = None


class KbDocumentOut(BaseModel):
    id: str
    title: str
    content: str
    doc_type: str
    metadata: dict | None
    file_path: str
    created_at: datetime
    updated_at: datetime


class KbSearchResult(BaseModel):
    id: str
    title: str
    content: str
    doc_type: str
    score: float


class KbSearchResponse(BaseModel):
    query: str
    results: list[KbSearchResult]


class KbTypeIn(BaseModel):
    name: str = Field(min_length=1, max_length=50)
    chapter: str = "商务文件"
    description: str = ""


class KbTypeOut(BaseModel):
    id: str
    name: str
    chapter: str
    description: str
    builtin: bool = False


class ProgressMessage(BaseModel):
    task_id: str
    progress: float
    message: str
    status: str
    stage: str
    estimated_time_remaining: int = 0


class HealthResponse(BaseModel):
    status: str
    version: str
    services: dict[str, str]


class SettingsOut(BaseModel):
    app_name: str
    system_env: str
    llm_provider: str
    tender_extract_url: str
    tender_extract_api_key: str = ""
    tender_llm_provider: str = "none"
    tender_llm_model: str = ""
    tender_llm_api_key: str = ""
    tender_llm_base_url: str = ""
    tender_llm_providers: list[dict] = Field(default_factory=list)
    biaoshu_skill_path: str
    use_vector_search: bool
    max_file_size: int
    max_extract_depth: int
    max_files_per_task: int


class SettingsUpdateIn(BaseModel):
    tender_extract_url: str | None = None
    tender_extract_api_key: str | None = None
    tender_llm_provider: str | None = None
    tender_llm_model: str | None = None
    tender_llm_api_key: str | None = None
    tender_llm_base_url: str | None = None
    tender_llm_providers: list[dict] | None = None
    biaoshu_skill_path: str | None = None
