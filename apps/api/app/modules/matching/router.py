"""Эндпоинты модуля matching: профиль компании и подборка кандидатов.

Company endpoints:
  POST  /api/v1/company   — создать компанию (один раз на одного работодателя).
  GET   /api/v1/company   — получить свою компанию.
  PATCH /api/v1/company   — изменить поля своей компании.

Candidates endpoint:
  GET   /api/v1/employer/candidates — отсортированный список кандидатов.

Детальные эндпоинты одного кандидата и его контакты обслуживаются модулем D
(`/employer/candidates/{candidate_id}` и `/employer/candidates/{candidate_id}/contacts`
в `app.modules.invitations.router`), поскольку они живут в privacy/invitation-потоке.
"""

from datetime import UTC
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.contracts.schemas import ActorContext, Role
from app.core.db import get_db, utcnow
from app.core.errors import ERROR_RESPONSES, AppError
from app.core.models import User
from app.core.security import require_role
from app.modules.fsp.provider import DemoFspProvider, FspProvider
from app.modules.matching import service
from app.modules.matching.models import Company
from app.modules.matching.schemas import (
    CandidateCard,
    CandidateList,
    CompanyCreate,
    CompanyResponse,
    CompanyUpdate,
    ReasonCard,
    SkillOnCard,
)

router = APIRouter(tags=["Matching"], responses=ERROR_RESPONSES)

EmployerActor = Annotated[ActorContext, Depends(require_role(Role.EMPLOYER))]
DbSession = Annotated[Session, Depends(get_db)]


def _fsp_provider(request: Request) -> FspProvider:
    """Берёт провайдер ФСП из app.state (регистрируется в create_app),
    иначе — локальный DemoFspProvider как фолбэк для тестов.
    """
    provider = getattr(request.app.state, "fsp_provider", None)
    if provider is None:
        provider = DemoFspProvider()
    return provider


FspPort = Annotated[FspProvider, Depends(_fsp_provider)]


# --- Company helpers ------------------------------------------------------


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


# --- Company endpoints ----------------------------------------------------


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
    # Serialize creation on both SQLite and PostgreSQL; a fresh request gets company_id.
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
    db.flush()  # присваивает company.id до коммита

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


# --- Candidates list ------------------------------------------------------


@router.get("/employer/candidates", response_model=CandidateList)
def list_candidates(
    actor: EmployerActor,
    db: DbSession,
    fsp: FspPort,
    specialization: Annotated[Literal["backend", "qa"] | None, Query()] = None,
    grade: Annotated[Literal["junior", "middle", "senior"] | None, Query()] = None,
    with_fsp_only: Annotated[bool, Query()] = False,
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
) -> CandidateList:
    """Отсортированная подборка опубликованных кандидатов.

    Подключение реального источника кандидатов (профили блока D с
    publication_enabled && discoverable && verified_category) — следующая
    итерация. Пока сервис возвращает пустой список; эндпоинт присутствует,
    чтобы фронт и e2e-сценарии видели корректный контракт.
    """
    _ = (actor, db, limit)
    ranked = service.rank_candidates(
        specialization=specialization,
        grade=grade,
        with_fsp_only=with_fsp_only,
        fsp_provider=fsp,
    )

    cards: list[CandidateCard] = []
    for item in ranked:
        c = item.candidate
        cards.append(
            CandidateCard(
                candidate_id=c["candidate_id"],
                display_name=c["display_name"],
                specialization=c["specialization"],
                verified_grade=c["verified_grade"],
                category_code=c["category_code"],
                experience_years=c.get("experience_years", 0),
                work_format=c.get("work_format", ""),
                declared_stack=c.get("declared_stack", []),
                score=item.score,
                components=item.components,
                skills=[SkillOnCard(id=s["id"], score=s["score"]) for s in c.get("skills", [])],
                fsp_status=item.fsp_signal.status,
                reasons=[ReasonCard(**r) for r in item.reasons],
            )
        )

    return CandidateList(items=cards, total=len(cards))
