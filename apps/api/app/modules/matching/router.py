"""Эндпоинты модуля matching: профиль компании, потребности, подборка кандидатов."""

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
from app.modules.matching.models import Company, EmployerNeed
from app.modules.matching.schemas import (
    CandidateCard,
    CandidateList,
    CategoryCard,
    CategoryList,
    CompanyCreate,
    CompanyResponse,
    CompanyUpdate,
    NeedCreate,
    NeedList,
    NeedResponse,
    ReasonCard,
    RequiredSkill,
    SkillOnCard,
)

router = APIRouter(tags=["Matching"], responses=ERROR_RESPONSES)

EmployerActor = Annotated[ActorContext, Depends(require_role(Role.EMPLOYER))]
DbSession = Annotated[Session, Depends(get_db)]


# --- Company ---------------------------------------------------------------


@router.post("/company", response_model=CompanyResponse, status_code=201)
def create_company(payload: CompanyCreate, actor: EmployerActor, db: DbSession) -> Company:
    existing = db.scalar(select(Company).where(Company.owner_user_id == str(actor.user_id)))
    if existing is not None:
        raise AppError(409, "COMPANY_EXISTS", "У вас уже есть компания. Используйте PATCH /company для обновления.")

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
    company = db.scalar(select(Company).where(Company.owner_user_id == str(actor.user_id)))
    if company is None:
        raise AppError(404, "COMPANY_NOT_FOUND", "Компания ещё не создана. Создайте через POST /company.")
    return company


@router.patch("/company", response_model=CompanyResponse)
def update_my_company(payload: CompanyUpdate, actor: EmployerActor, db: DbSession) -> Company:
    company = db.scalar(select(Company).where(Company.owner_user_id == str(actor.user_id)))
    if company is None:
        raise AppError(404, "COMPANY_NOT_FOUND", "Компания ещё не создана. Сначала выполните POST /company.")

    changes = payload.model_dump(exclude_unset=True)
    for key, value in changes.items():
        setattr(company, key, value)
    company.updated_at = utcnow()
    db.commit()
    db.refresh(company)
    return company


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
        created_at=need.created_at,
        updated_at=need.updated_at,
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


# --- Catalog & candidates --------------------------------------------------


@router.get("/employer/categories", response_model=CategoryList)
def list_categories(_: EmployerActor) -> CategoryList:
    items = [CategoryCard(**row) for row in service.category_stats()]
    return CategoryList(items=items)


@router.get("/employer/candidates", response_model=CandidateList)
def list_candidates(
    actor: EmployerActor,
    db: DbSession,
    specialization: Annotated[Literal["backend", "qa"] | None, Query()] = None,
    grade: Annotated[Literal["junior", "middle", "senior"] | None, Query()] = None,
    with_fsp_only: Annotated[bool, Query()] = False,
    need_id: Annotated[
        UUID | None,
        Query(description="Если указано — рейтинг рассчитывается по формуле с R."),
    ] = None,
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
) -> CandidateList:
    need_payload = None
    applied_need_id: UUID | None = None
    if need_id is not None:
        company_id = _require_company_id(db, actor)
        need = db.get(EmployerNeed, str(need_id))
        if need is None or need.company_id != company_id:
            raise AppError(404, "NEED_NOT_FOUND", "Потребность не найдена.")
        need_payload = {
            "specialization": need.specialization,
            "grades": list(need.grades),
            "required_skills": list(need.required_skills),
        }
        applied_need_id = UUID(need.id)

    ranked = service.rank_candidates(
        specialization=specialization,
        grade=grade,
        with_fsp_only=with_fsp_only,
        need=need_payload,
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

    return CandidateList(items=cards, total=len(ranked), applied_need_id=applied_need_id)
