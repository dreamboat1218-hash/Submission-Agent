from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from ..audit import log_action
from ..database import get_db
from ..models import User
from ..schemas import LoginRequest, TokenResponse, UserOut
from ..security import create_access_token, get_current_user, verify_password

router = APIRouter(prefix="/auth", tags=["认证"])


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, request: Request, db: Annotated[Session, Depends(get_db)]) -> TokenResponse:
    user = db.query(User).filter(User.username == payload.username).first()
    if user is None or not verify_password(payload.password, user.password_hash):
        log_action(db, "anonymous", "login_failed", payload.username, request=request, status="failed")
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    token = create_access_token(user)
    log_action(db, user.id, "login", user.username, request=request)
    return TokenResponse(token=token, user=UserOut(id=user.id, username=user.username, role=user.role))


@router.get("/me", response_model=UserOut)
def me(user: Annotated[User, Depends(get_current_user)]) -> UserOut:
    return UserOut(id=user.id, username=user.username, role=user.role)
