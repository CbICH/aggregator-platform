"""Эндпоинты модуля matching: профиль компании работодателя.

POST /api/v1/company   — создать компанию (один раз на одного работодателя).
GET  /api/v1/company   — получить свою компанию.
PATCH /api/v1/company  — изменить поля своей компании.
"""

from datetime import UTC
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from pydantic import ValidationError
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.contracts.schemas import ActorContext, Role
from app.core.db import get_db, utcnow
from app.core.errors import ERROR_RESPONSES, AppError
from app.core.models import User
from app.core.security import require_role
from app.modules.matching.models import Company, EmployerNeed
from app.modules.matching.schemas import (
    CandidateList,
    CategoryCode,
    CategoryList,
    CompanyCreate,
    CompanyResponse,
    CompanyUpdate,
    NeedCreate,
    NeedList,
    NeedResponse,
    RequiredSkill,
    SearchFilters,
    SearchHistory,
    SearchResponse,
)
from app.modules.matching.service import MatchingService
from app.modules.profiles.dependencies import port

router = APIRouter(tags=["Matching"], responses=ERROR_RESPONSES)

EmployerActor = Annotated[ActorContext, Depends(require_role(Role.EMPLOYER))]
DbSession = Annotated[Session, Depends(get_db)]


def response(company: Company) -> CompanyResponse:
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


def matching_service(request: Request, db: DbSession) -> MatchingService:
    return MatchingService(
        db,
        port(request.app, "profile_read", db),
        port(request.app, "assessment_read", db),
        port(request.app, "fsp_read", db),
    )


Service = Annotated[MatchingService, Depends(matching_service)]


# --- Helper: company id by actor -------------------------------------------


def _require_company_id(db: Session, actor: ActorContext) -> str:
    company = db.scalar(select(Company).where(Company.owner_user_id == str(actor.user_id)))
    if company is None:
        raise AppError(
            409,
            "COMPANY_REQUIRED",
            "Сначала заполните профиль компании (POST /company), затем создавайте потребности.",
        )
    return company.id


# --- Needs -----------------------------------------------------------------


def _need_to_response(need: EmployerNeed) -> NeedResponse:
    return NeedResponse(
        id=UUID(need.id),
        company_id=UUID(need.company_id),
        title=need.title,
        description=need.description,
        specialization=need.specialization,
        grades=need.grades,
        declared_stack=need.declared_stack,
        required_skills=[RequiredSkill(**rs) for rs in need.required_skills],
        work_format=need.work_format,
        salary_min=need.salary_min,
        salary_max=need.salary_max,
        created_at=need.created_at.replace(tzinfo=UTC)
        if need.created_at.tzinfo is None
        else need.created_at,
        updated_at=need.updated_at.replace(tzinfo=UTC)
        if need.updated_at.tzinfo is None
        else need.updated_at,
    )


@router.post("/employer/needs", response_model=NeedResponse, status_code=201)
def create_need(payload: NeedCreate, actor: EmployerActor, db: DbSession) -> NeedResponse:
    company_id = _require_company_id(db, actor)
    need = EmployerNeed(
        company_id=company_id,
        title=payload.title,
        description=payload.description,
        specialization=payload.specialization,
        grades=list(payload.grades),
        declared_stack=list(payload.declared_stack),
        required_skills=[rs.model_dump() for rs in payload.required_skills],
        work_format=payload.work_format,
        salary_min=payload.salary_min,
        salary_max=payload.salary_max,
    )
    db.add(need)
    db.commit()
    db.refresh(need)
    return _need_to_response(need)


@router.get("/employer/needs", response_model=NeedList)
def list_needs(actor: EmployerActor, db: DbSession) -> NeedList:
    company_id = _require_company_id(db, actor)
    rows = db.scalars(
        select(EmployerNeed)
        .where(EmployerNeed.company_id == company_id)
        .order_by(EmployerNeed.created_at.desc())
    ).all()
    return NeedList(items=[_need_to_response(n) for n in rows])


@router.get("/employer/needs/{need_id}", response_model=NeedResponse)
def get_need(need_id: UUID, actor: EmployerActor, db: DbSession) -> NeedResponse:
    company_id = _require_company_id(db, actor)
    need = db.get(EmployerNeed, str(need_id))
    if need is None or need.company_id != company_id:
        raise AppError(404, "NEED_NOT_FOUND", "Потребность не найдена.")
    return _need_to_response(need)


# --- Live matching and company search history -------------------------------


@router.get("/employer/categories", response_model=CategoryList)
def list_categories(actor: EmployerActor, service: Service) -> CategoryList:
    return service.categories(actor)


@router.get("/employer/matching/candidates", response_model=CandidateList)
def list_candidates(
    actor: EmployerActor,
    service: Service,
    specialization: Annotated[Literal["backend", "qa"] | None, Query()] = None,
    grade: Annotated[Literal["junior", "middle", "senior"] | None, Query()] = None,
    category_code: Annotated[CategoryCode | None, Query()] = None,
    stack: Annotated[list[str] | None, Query(max_length=20)] = None,
    with_fsp_only: Annotated[bool, Query()] = False,
    need_id: Annotated[UUID | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
    offset: Annotated[int, Query(ge=0, le=100000)] = 0,
) -> CandidateList:
    try:
        filters = SearchFilters(
            need_id=need_id,
            specialization=specialization,
            grade=grade,
            category_code=category_code,
            stack=stack or [],
            with_fsp_only=with_fsp_only,
        )
    except ValidationError:
        raise AppError(422, "INVALID_SEARCH_FILTERS", "Проверьте фильтры поиска") from None
    return service.search(actor, filters, limit=limit, offset=offset)


@router.post("/employer/searches", response_model=SearchResponse, status_code=201)
def create_search(payload: SearchFilters, actor: EmployerActor, db: DbSession, service: Service):
    result = service.create_snapshot(actor, payload)
    db.commit()
    return result


@router.get("/employer/searches", response_model=SearchHistory)
def search_history(
    actor: EmployerActor,
    service: Service,
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
    offset: Annotated[int, Query(ge=0, le=100000)] = 0,
):
    return service.history(actor, limit=limit, offset=offset)


@router.get("/employer/searches/{search_id}", response_model=SearchResponse)
def get_search(
    search_id: UUID,
    actor: EmployerActor,
    service: Service,
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
    offset: Annotated[int, Query(ge=0, le=100000)] = 0,
):
    return service.get_snapshot(actor, search_id, limit=limit, offset=offset)
