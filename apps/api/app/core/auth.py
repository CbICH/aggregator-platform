import logging
import secrets
from datetime import timedelta
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Request, Response
from pydantic import EmailStr, Field, field_validator
from sqlalchemy import delete, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.contracts.schemas import DTO, Role
from app.core.consent import CONSENT_TEXT, CONSENT_VERSION, SqlRegistrationConsent
from app.core.db import get_db, utcnow
from app.core.errors import ERROR_RESPONSES, AppError
from app.core.models import AuditEvent, EmailVerification, LoginSession, User
from app.core.rate_limit import auth_limits, rate_limit
from app.core.security import (
    CSRF_COOKIE,
    SESSION_COOKIE,
    Actor,
    digest,
    password_hasher,
    verify_password,
)

router = APIRouter(tags=["Authentication"], responses=ERROR_RESPONSES)
DB = Annotated[Session, Depends(get_db)]
logger = logging.getLogger(__name__)


class EmailRequest(DTO):
    email: EmailStr

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return value.lower()


class Credentials(EmailRequest):
    password: str = Field(min_length=12, max_length=128)


class RegisterRequest(Credentials):
    role: Role
    consent_accepted: Literal[True]
    consent_version: str


class VerifyRequest(DTO):
    token: str = Field(min_length=32, max_length=128)


class Message(DTO):
    message: str


class UserResponse(DTO):
    id: str
    email: EmailStr
    role: Role
    email_verified: bool
    company_id: str | None = None


class RegistrationPolicy(DTO):
    version: str
    text: str


def audit(db, request, action, user_id=None):
    db.add(
        AuditEvent(
            actor_id=user_id, action=action, object_id=user_id, request_id=request.state.request_id
        )
    )


def send_token(db, request, user):
    raw = secrets.token_urlsafe(32)
    db.add(
        EmailVerification(
            token_hash=digest(raw),
            user_id=user.id,
            expires_at=utcnow()
            + timedelta(minutes=request.app.state.settings.verification_minutes),
        )
    )
    # Persist account/token before SMTP; if delivery fails, resend can recover the account.
    db.commit()
    try:
        request.app.state.mailer.send_verification(user.email, raw)
    except (OSError, Exception) as exc:
        # Do not log SMTP exception text: it may include recipients or credentials.
        logger.warning(
            "verification_delivery_failed request_id=%s type=%s",
            request.state.request_id,
            type(exc).__name__,
        )
        raise AppError(
            503,
            "MAIL_UNAVAILABLE",
            "Аккаунт сохранён, но письмо не отправлено. Запросите новое письмо позже",
        ) from None


@router.get("/auth/registration-policy", response_model=RegistrationPolicy)
def registration_policy():
    return RegistrationPolicy(version=CONSENT_VERSION, text=CONSENT_TEXT)


@router.post("/auth/register", response_model=Message, status_code=202)
def register(payload: RegisterRequest, request: Request, db: DB):
    auth_limits(request, "register", str(payload.email))
    if payload.consent_version != CONSENT_VERSION:
        raise AppError(409, "CONSENT_VERSION_OUTDATED", "Обновите условия регистрации")
    encoded = password_hasher.hash(payload.password)
    existing = db.scalar(select(User).where(User.email == str(payload.email)))
    message = Message(message="Если адрес доступен для регистрации, на него отправлено письмо")
    if existing:
        return message
    user = User(email=str(payload.email), password_hash=encoded, role=payload.role.value)
    db.add(user)
    try:
        db.flush()
        SqlRegistrationConsent(db).record_registration(user.id, payload.consent_version)
        audit(db, request, "auth.registered", user.id)
        send_token(db, request, user)
    except IntegrityError:
        db.rollback()
        return message
    return message


@router.post("/auth/resend-verification", response_model=Message, status_code=202)
def resend_verification(payload: EmailRequest, request: Request, db: DB):
    auth_limits(request, "resend", str(payload.email))
    user = db.scalar(select(User).where(User.email == str(payload.email)))
    if user and not user.email_verified:
        # Existing unexpired links remain valid until any link is used. Anonymous resend
        # therefore cannot invalidate the owner's email through repeated requests.
        audit(db, request, "auth.verification_requested", user.id)
        send_token(db, request, user)
    return Message(message="Если адрес ожидает подтверждения, письмо отправлено")


@router.post("/auth/verify-email", response_model=Message)
def verify_email(payload: VerifyRequest, request: Request, db: DB):
    ip = request.client.host if request.client else "unknown"
    rate_limit(request, "verify:ip", ip, limit=30, seconds=60)
    now = utcnow()
    # Conditional UPDATE makes consumption atomic even for simultaneous requests.
    user_id = db.scalar(
        update(EmailVerification)
        .where(
            EmailVerification.token_hash == digest(payload.token),
            EmailVerification.used_at.is_(None),
            EmailVerification.expires_at > now,
        )
        .values(used_at=now)
        .returning(EmailVerification.user_id)
    )
    if user_id is None:
        raise AppError(400, "VERIFICATION_INVALID", "Ссылка недействительна или уже использована")
    db.execute(update(User).where(User.id == user_id).values(email_verified=True))
    db.execute(
        update(EmailVerification)
        .where(EmailVerification.user_id == user_id, EmailVerification.used_at.is_(None))
        .values(used_at=now)
    )
    audit(db, request, "auth.email_verified", user_id)
    db.commit()
    return Message(message="Email подтверждён. Можно продолжить работу")


@router.post("/auth/login", response_model=UserResponse)
def login(payload: Credentials, request: Request, response: Response, db: DB):
    auth_limits(request, "login", str(payload.email))
    user = db.scalar(select(User).where(User.email == str(payload.email)))
    if not verify_password(user.password_hash if user else None, payload.password):
        audit(db, request, "auth.login_failed")
        db.commit()
        raise AppError(401, "INVALID_CREDENTIALS", "Неверный email или пароль")
    token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
    old = request.cookies.get(SESSION_COOKIE)
    if old:
        db.execute(delete(LoginSession).where(LoginSession.token_hash == digest(old)))
    expires = utcnow() + timedelta(hours=request.app.state.settings.session_hours)
    db.add(
        LoginSession(
            token_hash=digest(token), csrf_hash=digest(csrf), user_id=user.id, expires_at=expires
        )
    )
    db.execute(
        delete(LoginSession).where(
            LoginSession.user_id == user.id, LoginSession.expires_at <= utcnow()
        )
    )
    audit(db, request, "auth.logged_in", user.id)
    db.commit()
    for name, value, http_only in [(SESSION_COOKIE, token, True), (CSRF_COOKIE, csrf, False)]:
        response.set_cookie(
            name,
            value,
            httponly=http_only,
            secure=request.app.state.settings.cookie_secure,
            samesite="lax",
            path="/",
            expires=expires,
        )
    return UserResponse.model_validate(user)


@router.get("/me", response_model=UserResponse)
def me(actor: Actor, request: Request):
    return UserResponse.model_validate(request.state.user)


@router.post("/auth/logout", response_model=Message)
def logout(actor: Actor, request: Request, response: Response, db: DB):
    db.delete(request.state.session)
    audit(db, request, "auth.logged_out", str(actor.user_id))
    db.commit()
    for name in (SESSION_COOKIE, CSRF_COOKIE):
        response.delete_cookie(
            name,
            path="/",
            secure=request.app.state.settings.cookie_secure,
            httponly=name == SESSION_COOKIE,
            samesite="lax",
        )
    return Message(message="Вы вышли из аккаунта")
