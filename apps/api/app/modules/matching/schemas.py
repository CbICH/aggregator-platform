"""Pydantic-схемы модуля matching.

Валидация входных/выходных данных для эндпоинтов работодателя.
"""

from typing import Annotated
from uuid import UUID

from pydantic import AwareDatetime, EmailStr, Field, field_validator

from app.contracts.schemas import DTO, CandidatePublic

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


# --- Candidates ------------------------------------------------------------


class CandidateList(DTO):
    """Отсортированный список публичных карточек кандидатов.

    Карточка — `CandidatePublic` из общих контрактов (`app.contracts.schemas`),
    собирается блоком D с учётом настроек приватности каждого кандидата.
    """

    items: list[CandidatePublic]
    total: int
