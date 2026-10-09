"""Эндпоинты модуля matching: профиль компании и подборка кандидатов.

Company endpoints:
  POST  /api/v1/company   — создать компанию (один раз на одного работодателя).
  GET   /api/v1/company   — получить свою компанию.
  PATCH /api/v1/company   — изменить поля своей компании.

Candidates endpoint:
  GET   /api/v1/employer/candidates — список публичных карточек опубликованных кандидатов.

Детальные эндпоинты одного кандидата и его контакты обслуживаются модулем D
(`/employer/candidates/{candidate_id}` и `/employer/candidates/{candidate_id}/contacts`
в `app.modules.invitations.router`), поскольку они живут в privacy/invitation-потоке.
"""

from datetime import UTC
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.contracts.schemas import ActorContext, CandidatePublic, Role
from app.core.db import get_db, utcnow
from app.core.errors import ERROR_RESPONSES, AppError
from app.core.models import User
from app.core.security import require_role
from app.modules.matching.models import Company
from app.modules.matching.schemas import (
    CandidateList,
    CompanyCreate,
    CompanyResponse,
    CompanyUpdate,
)

router = APIRouter(tags=["Matching"], responses=ERROR_RESPONSES)

EmployerActor = Annotated[ActorContext, Depends(require_role(Role.EMPLOYER))]
DbSession = Annotated[Session, Depends(get_db)]


# --- Company helpers ------------------------------------------------------


def response(company: Company) -> CompanyResponse:
    """Сериализация Company → CompanyResponse с нормализацией tzinfo."""
    data = {name: getattr(company, name) for name in CompanyResponse.model_fields}
    for field in ("created_at", "updated_at"):
        if data[field].tzinfo is None:
            data[field] = data[field].replace(tzinfo=UTC)
    return CompanyResponse.model_validate(data)


# --- Company endpoints ----------------------------------------------------


@router.post("/company", response_model=CompanyResponse, status_code=201)
def create_company(
    payload: CompanyCreate,
    actor: EmployerActor,
    db: DbSession,
) -> CompanyResponse:
    """Создать компанию для текущего работодателя."""
    db.execute(update(User).where(User.id == str(actor.user_id)).values(company_id=User.company_id))
    existing = db.scalar(select(Company).where(Company.owner_user_id == str(actor.user_id)))
    if existing is not None:
        raise AppError(
            409,
            "COMPANY_EXISTS",
            "У вас уже есть компания. Используйте PATCH /company для обновления.",
        )

    company = Company(
        owner_user_id=str(actor.user_id),
        name=payload.name,
        description=payload.description,
        industry=payload.industry,
        city=payload.city,
        contact_name=payload.contact_name,
        contact_role=payload.contact_role,
        contact_email=payload.contact_email,
    )
    db.add(company)
    db.flush()

    user = db.get(User, str(actor.user_id))
    if user is not None:
        user.company_id = company.id

    db.commit()
    db.refresh(company)
    return response(company)


@router.get("/company", response_model=CompanyResponse)
def get_my_company(actor: EmployerActor, db: DbSession) -> CompanyResponse:
    company = db.scalar(select(Company).where(Company.owner_user_id == str(actor.user_id)))
    if company is None:
        raise AppError(
            404, "COMPANY_NOT_FOUND", "Компания ещё не создана. Создайте через POST /company."
        )
    return response(company)


@router.patch("/company", response_model=CompanyResponse)
def update_my_company(
    payload: CompanyUpdate,
    actor: EmployerActor,
    db: DbSession,
) -> CompanyResponse:
    company = db.scalar(select(Company).where(Company.owner_user_id == str(actor.user_id)))
    if company is None:
        raise AppError(
            404,
            "COMPANY_NOT_FOUND",
            "Компания ещё не создана. Сначала выполните POST /company.",
        )

    changes = payload.model_dump(exclude_unset=True)
    for key, value in changes.items():
        setattr(company, key, value)
    company.updated_at = utcnow()
    db.commit()
    db.refresh(company)
    return response(company)


# --- Candidates list ------------------------------------------------------


@router.get("/employer/candidates", response_model=CandidateList)
def list_candidates(
    request: Request,
    actor: EmployerActor,
    db: DbSession,
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
) -> CandidateList:
    """Публичные карточки опубликованных кандидатов.

    Источник — порт `profile_read_factory` блока D: читает профили с
    `publication_enabled && discoverable && verified_category`. Поля карточки
    (роли, стек, опыт) приходят с учётом настроек приватности каждого
    кандидата; скрытые поля перечислены в `hidden_fields`.

    Fail-closed: без порта `company_read_factory` эндпоинт отвечает 503 —
    защита от неполной настройки прода.
    """
    if getattr(request.app.state, "company_read_factory", None) is None:
        raise AppError(503, "DATABASE_UNAVAILABLE", "Порт company_read недоступен")
    profile_read_factory = getattr(request.app.state, "profile_read_factory", None)
    if profile_read_factory is None:
        raise AppError(503, "DATABASE_UNAVAILABLE", "Порт profile_read недоступен")

    profiles: list[CandidatePublic] = profile_read_factory(db).list_public(actor, limit=limit)
    return CandidateList(items=profiles, total=len(profiles))
