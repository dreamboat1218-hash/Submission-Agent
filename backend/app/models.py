from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_uuid)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(256))
    role: Mapped[str] = mapped_column(String(20), default="user")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class Task(Base):
    __tablename__ = "tasks"
    __table_args__ = (
        Index("idx_tasks_user_id", "user_id"),
        Index("idx_tasks_status", "status"),
        Index("idx_tasks_source", "source"),
        Index("idx_tasks_created_at", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String(64), default="system")
    status: Mapped[str] = mapped_column(String(20), default="created")
    current_stage: Mapped[str] = mapped_column(String(30), default="preprocess")
    progress: Mapped[float] = mapped_column(Float, default=0.0)
    message: Mapped[str] = mapped_column(Text, default="")
    original_file_name: Mapped[str] = mapped_column(String(255), default="")
    original_file_path: Mapped[str] = mapped_column(String(512), default="")
    work_dir: Mapped[str] = mapped_column(String(512), default="")
    file_count: Mapped[int] = mapped_column(Integer, default=0)
    manifest: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    extracted_data: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    industry: Mapped[str] = mapped_column(String(50), default="通用")
    bid_file_path: Mapped[str] = mapped_column(String(512), default="")
    check_result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    mode: Mapped[str] = mapped_column(String(20), default="fast")
    source: Mapped[str] = mapped_column(String(20), default="workbench")
    error_message: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class KbDocument(Base):
    __tablename__ = "kb_documents"
    __table_args__ = (Index("idx_kb_documents_type", "doc_type"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_uuid)
    title: Mapped[str] = mapped_column(String(255), index=True)
    content: Mapped[str] = mapped_column(Text, default="")
    doc_type: Mapped[str] = mapped_column(String(50), default="企业资质")
    metadata_json: Mapped[dict | None] = mapped_column("metadata", JSON, nullable=True)
    vector_id: Mapped[str] = mapped_column(String(128), default="")
    file_path: Mapped[str] = mapped_column(String(512), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)


class KbType(Base):
    __tablename__ = "kb_types"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    chapter: Mapped[str] = mapped_column(String(30), default="商务文件")
    description: Mapped[str] = mapped_column(Text, default="")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class IndustryTemplate(Base):
    __tablename__ = "industry_templates"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_uuid)
    industry: Mapped[str] = mapped_column(String(50), index=True)
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(Text, default="")
    file_path: Mapped[str] = mapped_column(String(512), default="")
    version: Mapped[str] = mapped_column(String(20), default="1.0")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)


class OperationLog(Base):
    __tablename__ = "operation_logs"
    __table_args__ = (
        Index("idx_ops_user_id", "user_id"),
        Index("idx_ops_created_at", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String(64), default="system")
    action: Mapped[str] = mapped_column(String(50))
    resource: Mapped[str] = mapped_column(String(255), default="")
    detail: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    ip_address: Mapped[str] = mapped_column(String(45), default="")
    user_agent: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(20), default="success")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
