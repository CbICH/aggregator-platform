"""Эндпоинты модуля matching: профиль компании работодателя и подборка.

Company:
  POST  /api/v1/company              — создать компанию (одна на одного работодателя).
  GET   /api/v1/company              — получить свою компанию.
  PATCH /api/v1/company              — изменить поля своей компании.

Catalog + поиск:
  GET   /api/v1/employer/categories  — активные категории с количеством кандидатов.
  GET   /api/v1/employer/candidates  — список кандидатов с объяснимым score.
"""

from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.contracts.schemas import ActorContext, Role
from app.core.db import get_db, utcnow
from app.core.errors import ERROR_RESPONSES, AppError
from app.core.models import User
from app.core.security import require_role
from app.modules.matching import service
from app.modules.matching.models import Company
from app.modules.matching.schemas import (
    CandidateCard,
    CandidateList,
    CategoryCard,
    CategoryList,
    CompanyCreate,
    CompanyResponse,
    CompanyUpdate,
    ReasonCard,
    SkillOnCard,
)

router = APIRouter(tags=["Matching"], responses=ERROR_RESPONSES)

EmployerActor = Annotated[ActorContext, Depends(require_role(Role.EMPLOYER))]
DbSession = Annotated[Session, Depends(get_db)]


# --- Company ---------------------------------------------------------------


@router.post("/company", response_model=CompanyResponse, status_code=201)
def create_company(
    payload: CompanyCreate,
    actor: EmployerActor,
    db: DbSession,
) -> Company:
    """Создать компанию для текущего работодателя.

    Возвращает 409 COMPANY_EXISTS, если у работодателя уже есть компания.
    """
    existing = db.scalar(
        select(Company).where(Company.owner_user_id == str(actor.user_id))
    )
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
    return company


@router.get("/company", response_model=CompanyResponse)
def get_my_company(actor: EmployerActor, db: DbSession) -> Company:
    """Прочитать профиль своей компании."""
    company = db.scalar(
        select(Company).where(Company.owner_user_id == str(actor.user_id))
    )
    if company is None:
        raise AppError(
            404, "COMPANY_NOT_FOUND", "Компания ещё не создана. Создайте через POST /company."
        )
    return company


@router.patch("/company", response_model=CompanyResponse)
def update_my_company(
    payload: CompanyUpdate,
    actor: EmployerActor,
    db: DbSession,
) -> Company:
    """Частично обновить свою компанию."""
    company = db.scalar(
        select(Company).where(Company.owner_user_id == str(actor.user_id))
    )
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
    return company


# --- Catalog ---------------------------------------------------------------


@router.get("/employer/categories", response_model=CategoryList)
def list_categories(_: EmployerActor) -> CategoryList:
    """Активные категории с количеством доступных кандидатов.

    Пока работает на демонстрационных fixtures; после seed'а БД переключится
    на запросы к базе без изменения формы ответа.
    """
    items = [CategoryCard(**row) for row in service.category_stats()]
    return CategoryList(items=items)


# --- Candidates ------------------------------------------------------------


@router.get("/employer/candidates", response_model=CandidateList)
def list_candidates(
    _: EmployerActor,
    specialization: Annotated[
        Literal["backend", "qa"] | None,
        Query(description="Фильтр по специализации кандидата."),
    ] = None,
    grade: Annotated[
        Literal["junior", "middle", "senior"] | None,
        Query(description="Фильтр по подтверждённому грейду."),
    ] = None,
    with_fsp_only: Annotated[
        bool,
        Query(description="Показывать только кандидатов с достижениями ФСП."),
    ] = False,
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
) -> CandidateList:
    """Подборка кандидатов с объяснимым score.

    Формула (упрощённая, без потребности):
      score = 0.90 * test_score + 0.10 * fsp_signal

    После добавления /employer/needs и /employer/searches формула перейдёт
    на `0.65*T + 0.25*R + 0.10*F` без изменения внешнего контракта.
    """
    ranked = service.rank_candidates(
        specialization=specialization,
        grade=grade,
        with_fsp_only=with_fsp_only,
    )

    cards: list[CandidateCard] = []
    for item in ranked[:limit]:
        c = item.candidate
        cards.append(
            CandidateCard(
                candidate_id=UUID(c["candidate_id"]),
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
                fsp_status=c.get("fsp", {}).get("status", "not_linked"),
                reasons=[ReasonCard(**r) for r in item.reasons],
            )
        )

    return CandidateList(items=cards, total=len(ranked))
