"""Эндпоинты модуля matching: профиль компании работодателя.

POST /api/v1/company   — создать компанию (один раз на одного работодателя).
GET  /api/v1/company   — получить свою компанию.
PATCH /api/v1/company  — изменить поля своей компании.

Эндпоинты подборки кандидатов (`/employer/candidates`,
`/employer/candidates/{candidate_id}`, `/employer/candidates/{candidate_id}/contacts`)
обслуживаются модулем D (`app.modules.invitations.router`), поскольку живут в
privacy/invitation-потоке и опираются на профиль блока D с учётом настроек
приватности каждого кандидата.
"""

from datetime import UTC
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.contracts.schemas import ActorContext, Role
from app.core.db import get_db, utcnow
from app.core.errors import ERROR_RESPONSES, AppError
from app.core.models import User
from app.core.security import require_role
from app.modules.matching.models import Company
from app.modules.matching.schemas import CompanyCreate, CompanyResponse, CompanyUpdate

router = APIRouter(tags=["Matching"], responses=ERROR_RESPONSES)

EmployerActor = Annotated[ActorContext, Depends(require_role(Role.EMPLOYER))]
DbSession = Annotated[Session, Depends(get_db)]


def response(company: Company) -> CompanyResponse:
    """Сериализация Company → CompanyResponse с нормализацией tzinfo.

    SQLite возвращает naive datetime; продовский PostgreSQL — aware. API-схема
    требует AwareDatetime, поэтому подставляем UTC, если tzinfo отсутствует.
    """
    data = {name: getattr(company, name) for name in CompanyResponse.model_fields}
    for field in ("created_at", "updated_at"):
        if data[field].tzinfo is None:
            data[field] = data[field].replace(tzinfo=UTC)
    return CompanyResponse.model_validate(data)


@router.post("/company", response_model=CompanyResponse, status_code=201)
def create_company(
    payload: CompanyCreate,
    actor: EmployerActor,
    db: DbSession,
) -> CompanyResponse:
    """Создать компанию для текущего работодателя.

    Возвращает 409 COMPANY_EXISTS, если у работодателя уже есть компания.
    После успешного создания company_id записывается в users.company_id, чтобы
    ActorContext в следующих запросах содержал связь.
    """
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
    """Прочитать профиль своей компании.

    Возвращает 404 COMPANY_NOT_FOUND, если компания ещё не создана.
    """
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
    """Частично обновить свою компанию.

    Отправленные поля применяются; пропущенные остаются как были.
    """
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
