from typing import Annotated, Literal
from uuid import UUID

from pydantic import AwareDatetime, Field, field_validator, model_validator

from app.contracts.schemas import DTO, InvitationStatus, Salary


class InvitationCreate(DTO):
    candidate_id: UUID
    need_id: UUID | None = None
    vacancy_id: UUID | None = None
    description: str = Field(min_length=20, max_length=6000)
    salary: Salary
    company_contact: str = Field(min_length=3, max_length=300)
    evidence_refs: list[Annotated[str, Field(min_length=1, max_length=80)]] = Field(
        default_factory=list, max_length=30
    )

    @field_validator("description", "company_contact")
    @classmethod
    def meaningful(cls, value, info):
        value = value.strip()
        if len(value) < (20 if info.field_name == "description" else 3):
            raise ValueError("Заполните описание предложения и способ связи")
        return value

    @field_validator("evidence_refs")
    @classmethod
    def unique_refs(cls, value):
        return list(dict.fromkeys(value))


class InvitationDecision(DTO):
    action: Literal["accept", "decline"]
    expected_version: Annotated[int, Field(strict=True, ge=1)]
    contact_consent_accepted: bool = Field(default=False, strict=True)
    contact_consent_version: str | None = Field(default=None, max_length=50)

    @model_validator(mode="after")
    def acceptance(self):
        if self.action == "accept" and (
            not self.contact_consent_accepted or not self.contact_consent_version
        ):
            raise ValueError("Для принятия предложения разрешите передачу контактов этой компании")
        if self.action == "decline" and (
            self.contact_consent_accepted or self.contact_consent_version is not None
        ):
            raise ValueError("Отклонение не передаёт контакты")
        return self


class InvitationEvidence(DTO):
    skill_id: str
    score: float
    assessment_id: UUID
    assessment_version: str


class InvitationResponse(DTO):
    invitation_id: UUID
    candidate_id: UUID
    candidate_alias: str
    company_id: UUID
    company_name: str
    need_id: UUID | None = None
    vacancy_id: UUID | None = None
    description: str
    salary: Salary
    company_contact: str
    category_code: str | None = None
    evidence: list[InvitationEvidence]
    status: InvitationStatus
    version: int
    created_at: AwareDatetime
    viewed_at: AwareDatetime | None = None
    decided_at: AwareDatetime | None = None
    contact_access_active: bool


class InvitationListResponse(DTO):
    items: list[InvitationResponse]
    next_cursor: UUID | None = None
    limit: int


class EmployerInvitationContext(DTO):
    company_id: UUID
    company_name: str
    company_contact: str


class InvitationEventResponse(DTO):
    old_status: InvitationStatus | None = None
    new_status: InvitationStatus
    created_at: AwareDatetime


class InvitationHistory(DTO):
    items: list[InvitationEventResponse]
