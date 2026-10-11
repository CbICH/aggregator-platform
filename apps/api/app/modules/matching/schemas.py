"""Pydantic-схемы модуля matching.

Валидация входных/выходных данных для эндпоинтов работодателя.
"""

from typing import Annotated, Literal
from uuid import UUID

from pydantic import AwareDatetime, EmailStr, Field, field_validator, model_validator

from app.contracts.schemas import DTO, CandidatePublic, FspAchievementEvidence


class CompanyCreate(DTO):
    """Тело POST /company — что присылает фронт при создании компании."""

    name: Annotated[str, Field(min_length=2, max_length=120)]
    description: Annotated[str, Field(min_length=10, max_length=2000)]
    industry: Annotated[str, Field(min_length=2, max_length=40)]
    city: Annotated[str, Field(min_length=2, max_length=80)]
    contact_name: Annotated[str, Field(min_length=2, max_length=120)]
    contact_role: Annotated[str, Field(max_length=80)] | None = None
    contact_email: EmailStr

    @field_validator("name", "description", "industry", "city", "contact_name", mode="before")
    @classmethod
    def trim_fields(cls, value):
        return value.strip() if isinstance(value, str) else value


class CompanyUpdate(DTO):
    """Тело PATCH /company — частичное обновление, все поля опциональны."""

    name: Annotated[str, Field(min_length=2, max_length=120)] | None = None
    description: Annotated[str, Field(min_length=10, max_length=2000)] | None = None
    industry: Annotated[str, Field(min_length=2, max_length=40)] | None = None
    city: Annotated[str, Field(min_length=2, max_length=80)] | None = None
    contact_name: Annotated[str, Field(min_length=2, max_length=120)] | None = None
    contact_role: Annotated[str, Field(max_length=80)] | None = None
    contact_email: EmailStr | None = None

    @field_validator(
        "name", "description", "industry", "city", "contact_name", "contact_email", mode="before"
    )
    @classmethod
    def required_fields_cannot_be_cleared(cls, value):
        if value is None:
            raise ValueError("Пропустите поле вместо отправки null")
        return value.strip() if isinstance(value, str) else value


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


class CandidateCard(CandidatePublic):
    """Публичная карточка кандидата в выдаче работодателю."""

    candidate_id: UUID
    display_name: str
    specialization: Literal["backend", "qa"]
    verified_grade: Literal["junior", "middle", "senior"]
    category_code: str
    experience_years: float | None = Field(default=None, ge=0)
    score: float = Field(ge=0, le=100)
    components: dict[str, float]
    skills: list[SkillOnCard]
    fsp_status: Literal["not_linked", "linked_empty", "linked_with_data", "unavailable"]
    fsp_source: Literal["demo", "registry"]
    fsp_achievements: list[FspAchievementEvidence] = Field(default_factory=list)
    reasons: list[ReasonCard]


class CandidateList(DTO):
    """Отсортированный список кандидатов для работодателя."""

    items: list[CandidateCard]
    total: int
    applied_need_id: UUID | None = None
    limit: int = 20
    next_offset: int | None = None


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
    grades: Annotated[
        list[Literal["junior", "middle", "senior"]], Field(min_length=1, max_length=3)
    ]
    declared_stack: Annotated[
        list[Annotated[str, Field(min_length=1, max_length=30)]], Field(max_length=20)
    ] = []
    required_skills: Annotated[list[RequiredSkill], Field(min_length=1, max_length=10)]
    work_format: Literal["remote", "hybrid", "office"]
    salary_min: Annotated[int, Field(gt=0, le=10_000_000)] | None = None
    salary_max: Annotated[int, Field(gt=0, le=10_000_000)] | None = None

    @field_validator("title", "description", mode="before")
    @classmethod
    def trim_text(cls, value):
        return value.strip() if isinstance(value, str) else value

    @field_validator("declared_stack")
    @classmethod
    def normalize_stack(cls, value):
        if any(not tag.strip() for tag in value):
            raise ValueError("Стек не может содержать пустые значения")
        return list(dict.fromkeys(tag.strip().lower() for tag in value))

    @field_validator("grades")
    @classmethod
    def unique_grades(cls, value):
        return list(dict.fromkeys(value))

    @model_validator(mode="after")
    def valid_salary(self):
        from app.core.catalogs import catalogs

        allowed = {skill.id for skill in catalogs().skills}
        skills = [skill.id for skill in self.required_skills]
        if len(skills) != len(set(skills)) or any(skill not in allowed for skill in skills):
            raise ValueError("Выберите уникальные навыки из справочника")
        if any((skill.startswith("qa.")) != (self.specialization == "qa") for skill in skills):
            raise ValueError("Навыки должны соответствовать специализации")
        if (self.salary_min is None) != (self.salary_max is None):
            raise ValueError("Укажите обе границы зарплаты либо оставьте их пустыми")
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


CategoryCode = Literal[
    "backend:junior", "backend:middle", "backend:senior", "qa:junior", "qa:middle", "qa:senior"
]


class SearchFilters(DTO):
    need_id: UUID | None = None
    specialization: Literal["backend", "qa"] | None = None
    grade: Literal["junior", "middle", "senior"] | None = None
    category_code: CategoryCode | None = None
    stack: list[Annotated[str, Field(min_length=1, max_length=50)]] = Field(
        default_factory=list, max_length=20
    )
    with_fsp_only: bool = Field(default=False, strict=True)

    @field_validator("stack")
    @classmethod
    def normalize_stack(cls, value):
        if any(not tag.strip() for tag in value):
            raise ValueError("Введите названия технологий")
        return list(dict.fromkeys(tag.strip().lower() for tag in value))


class SearchSummary(DTO):
    id: UUID
    created_at: AwareDatetime
    filters: SearchFilters
    original_total: int
    need_title: str | None = None


class SearchResponse(CandidateList, SearchSummary):
    unavailable_count: int = 0


class SearchHistory(DTO):
    items: list[SearchSummary]
    next_offset: int | None = None
