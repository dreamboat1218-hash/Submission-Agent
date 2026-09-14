from __future__ import annotations

from datetime import datetime, timezone

from fastapi import Request
from sqlalchemy.orm import Session

from .models import OperationLog


def log_action(
    db: Session,
    user_id: str,
    action: str,
    resource: str = "",
    detail: dict | None = None,
    request: Request | None = None,
    status: str = "success",
) -> None:
    ip_address = ""
    user_agent = ""
    if request is not None:
        forwarded = request.headers.get("X-Forwarded-For")
        ip_address = forwarded.split(",")[0].strip() if forwarded else (request.client.host if request.client else "")
        user_agent = request.headers.get("User-Agent", "")
    db.add(
        OperationLog(
            user_id=user_id,
            action=action,
            resource=resource,
            detail=detail,
            ip_address=ip_address,
            user_agent=user_agent,
            status=status,
            created_at=datetime.now(timezone.utc),
        )
    )
    db.commit()
