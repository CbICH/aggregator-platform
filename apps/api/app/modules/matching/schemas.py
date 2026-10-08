"""Pydantic-схемы модуля matching.

Валидация входных/выходных данных для эндпоинтов работодателя.
"""

from typing import Annotated, Literal
from uuid import UUID

from pydantic import AwareDatetime, EmailStr, Field, model_validator

from app.contracts.schemas import DTO


# --- Company ---------------------------------------------------------------


class CompanyCreate(DTO):
    """Тело POST /company — что присылает фронт при создании компании."""

    name: Annotated[str, Field(min_length=2, max_length=120)]
    description: Annotated[str, Field(min_length=10, max_length=2000)]
    industry: Annotated[str, Field(min_length=2, max_length=40)]
    city: Annotated[str, Field(min_length=2, max_length=80)]
    contact_name: Annotated[str, Field(min_length=2, max_length=120)]
    contact_role: Annotated[str, Field(max_length=80)] | None = None
    contact_email: EmailStr


class CompanyUpdate(DTO):
    """Тело PATCH /company — частичное обновление, все поля опциональны."""

    name: Annotated[str, Field(min_length=2, max_length=120)] | None = None
    description: Annotated[str, Field(min_length=10, max_length=2000)] | None = None
    industry: Annotated[str, Field(min_length=2, max_length=40)] | None = None
    city: Annotated[str, Field(min_length=2, max_length=80)] | None = None
    contact_name: Annotated[str, Field(min_length=2, max_length=120)] | None = None
    contact_role: Annotated[str, Field(max_length=80)] | None = None
    contact_email: EmailStr | None = None


class CompanyResponse(DTO):
    """Что API возвращает в ответе — полный профиль компании владельца."""

    id: UUID
    name: str
    description: str
    industry: str
    city: str
    contact_name: str
    contact_role: str | None = None
    contact_email: EmailStr
    created_at: AwareDatetime
    updated_at: AwareDatetime


# --- Catalog / Categories --------------------------------------------------


class CategoryCard(DTO):
    """Короткая справочная карточка категории с количеством кандидатов."""

    code: str
    specialization: Literal["backend", "qa"]
    grade: Literal["junior", "middle", "senior"]
    active: bool
    candidate_count: int


class CategoryList(DTO):
    items: list[CategoryCard]


# --- Candidates ------------------------------------------------------------


class SkillOnCard(DTO):
    """Навык с баллом внутри карточки кандидата."""

    id: str
    score: float = Field(ge=0, le=100)


class ReasonCard(DTO):
    """Одна строка «почему подходит» в карточке кандидата."""

    code: str
    label: str | None = None
    skill_id: str | None = None
    score: float | None = Field(default=None, ge=0, le=100)
    date: str | None = None


class CandidateCard(DTO):
    """Публичная карточка кандидата в выдаче работодателю."""

    candidate_id: UUID
    display_name: str
    specialization: Literal["backend", "qa"]
    verified_grade: Literal["junior", "middle", "senior"]
    category_code: str
    experience_years: int
    work_format: str
    declared_stack: list[str]
    score: float = Field(ge=0, le=100)
    components: dict[str, float]
    skills: list[SkillOnCard]
    fsp_status: Literal["not_linked", "linked_empty", "linked_with_data", "unavailable"]
    reasons: list[ReasonCard]


class CandidateList(DTO):
    """Отсортированный список кандидатов для работодателя."""

    items: list[CandidateCard]
    total: int
    applied_need_id: UUID | None = None


# --- Needs (employer) ------------------------------------------------------


class RequiredSkill(DTO):
    """Проверяемый навык с весом внутри потребности."""

    id: Annotated[str, Field(min_length=2, max_length=60)]
    weight: Annotated[int, Field(ge=1, le=5)] = 1


class NeedCreate(DTO):
    """Тело POST /employer/needs — что присылает фронт при создании потребности."""

    title: Annotated[str, Field(min_length=4, max_length=160)]
    description: Annotated[str, Field(min_length=10, max_length=2000)]
    specialization: Literal["backend", "qa"]
    grades: Annotated[list[Literal["junior", "middle", "senior"]], Field(min_length=1, max_length=3)]
    declared_stack: Annotated[list[Annotated[str, Field(min_length=1, max_length=30)]], Field(max_length=20)] = []
    required_skills: Annotated[list[RequiredSkill], Field(min_length=1, max_length=10)]
    work_format: Literal["remote", "hybrid", "office"]
    salary_min: Annotated[int, Field(gt=0, le=10_000_000)] | None = None
    salary_max: Annotated[int, Field(gt=0, le=10_000_000)] | None = None

    @model_validator(mode="after")
    def valid_salary(self):
        if self.salary_min is not None and self.salary_max is not None:
            if self.salary_min > self.salary_max:
                raise ValueError("salary_min must not exceed salary_max")
        return self


class NeedResponse(DTO):
    id: UUID
    company_id: UUID
    title: str
    description: str
    specialization: Literal["backend", "qa"]
    grades: list[Literal["junior", "middle", "senior"]]
    declared_stack: list[str]
    required_skills: list[RequiredSkill]
    work_format: Literal["remote", "hybrid", "office"]
    salary_min: int | None = None
    salary_max: int | None = None
    created_at: AwareDatetime
    updated_at: AwareDatetime


class NeedList(DTO):
    items: list[NeedResponse]
