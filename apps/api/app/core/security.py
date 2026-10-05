import hashlib
import secrets
from typing import Annotated

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from fastapi import Depends, Request, Security
from fastapi.security import APIKeyCookie
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.contracts.schemas import ActorContext, Role
from app.core.db import get_db, utcnow
from app.core.errors import AppError
from app.core.models import LoginSession, User

SESSION_COOKIE = "signal_session"
CSRF_COOKIE = "signal_csrf"
password_hasher = PasswordHasher()
_DUMMY_HASH = password_hasher.hash(secrets.token_urlsafe(32))
session_cookie = APIKeyCookie(name=SESSION_COOKIE, auto_error=False)


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def verify_password(encoded: str | None, password: str) -> bool:
    try:
        valid = password_hasher.verify(encoded or _DUMMY_HASH, password)
        return bool(encoded and valid)
    except (VerificationError, InvalidHashError):
        return False


def current_actor(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    token: Annotated[str | None, Security(session_cookie)] = None,
) -> ActorContext:
    if not token or len(token) > 200:
        raise AppError(401, "AUTH_REQUIRED", "Войдите в аккаунт")
    record = db.scalar(
        select(LoginSession).where(
            LoginSession.token_hash == digest(token), LoginSession.expires_at > utcnow()
        )
    )
    if record is None:
        raise AppError(401, "SESSION_EXPIRED", "Сессия завершена. Войдите снова")
    user = db.get(User, record.user_id)
    if user is None:
        raise AppError(401, "AUTH_REQUIRED", "Войдите в аккаунт")
    if request.method not in {"GET", "HEAD", "OPTIONS"}:
        csrf = request.headers.get("X-CSRF-Token", "")
        if not csrf or not secrets.compare_digest(digest(csrf), record.csrf_hash):
            raise AppError(403, "CSRF_INVALID", "Обновите страницу и повторите действие")
    request.state.session = record
    request.state.user = user
    return ActorContext(
        user_id=user.id,
        role=user.role,
        email_verified=user.email_verified,
        company_id=user.company_id,
    )


Actor = Annotated[ActorContext, Depends(current_actor)]


def require_role(role: Role, *, verified: bool = True):
    def dependency(actor: Actor) -> ActorContext:
        if actor.role != role:
            raise AppError(403, "ROLE_FORBIDDEN", "Действие недоступно для этой роли")
        if verified and not actor.email_verified:
            raise AppError(403, "EMAIL_NOT_VERIFIED", "Подтвердите email")
        return actor

    return dependency
