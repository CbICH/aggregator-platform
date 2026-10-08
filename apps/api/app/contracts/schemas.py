from enum import StrEnum
from typing import Annotated, Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator


class DTO(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)


class Role(StrEnum):
    CANDIDATE = "candidate"
    EMPLOYER = "employer"


class ActorContext(DTO):
    user_id: UUID
    role: Role
    email_verified: bool
    company_id: UUID | None = None


class Salary(DTO):
    min: Annotated[int, Field(strict=True, gt=0, le=2147483647)]
    max: Annotated[int, Field(strict=True, gt=0, le=2147483647)]
    currency: Literal["RUB"] = "RUB"
    period: Literal["month"] = "month"
    tax_basis: Literal["gross"] = "gross"

    @model_validator(mode="after")
    def valid_range(self):
        if self.min > self.max:
            raise ValueError("min must not exceed max")
        return self


class SkillEvidence(DTO):
    id: str
    score: float = Field(ge=0, le=100)
    source: Literal["assessment"] = "assessment"


class VerifiedCategory(DTO):
    candidate_id: UUID
    category_code: str
    specialization: Literal["backend", "qa"]
    verified_grade: Literal["junior", "middle", "senior"]
    test_score: float = Field(ge=0, le=100)
    assessment_id: UUID
    assessment_version: str
    assigned_at: AwareDatetime
    next_change_at: AwareDatetime
    skills: list[SkillEvidence]

    @model_validator(mode="after")
    def category_matches(self):
        if self.category_code != f"{self.specialization}:{self.verified_grade}":
            raise ValueError("category_code must match specialization and verified_grade")
        if self.next_change_at < self.assigned_at:
            raise ValueError("next_change_at precedes assigned_at")
        return self


class CandidatePublic(DTO):
    candidate_id: UUID
    display_name: str
    declared_stack: list[str] | None = None
    roles: list[str] | None = None
    experience_months: int | None = Field(default=None, ge=0)
    hidden_fields: list[str] = Field(default_factory=list)
    verified_category: VerifiedCategory | None = None


class CompanySummary(DTO):
    company_id: UUID
    name: str
    contact: str


class FspEvidence(DTO):
    status: Literal["not_linked", "linked_empty", "linked_with_data", "unavailable"]
    signal: float = Field(default=0, ge=0, le=100)
    source: Literal["demo", "registry"] = "demo"
    fetched_at: AwareDatetime | None = None


class CandidateContacts(DTO):
    candidate_id: UUID
    email: str | None = None
    phone: str | None = None
    contact_method: str = ""


class InvitationStatus(StrEnum):
    SENT = "sent"
    VIEWED = "viewed"
    ACCEPTED = "accepted"
    DECLINED = "declined"
