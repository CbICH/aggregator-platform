from datetime import datetime
from enum import StrEnum
from typing import Annotated, Any, Literal
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
    min: Annotated[int, Field(strict=True, gt=0)]
    max: Annotated[int, Field(strict=True, gt=0)]
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
    declared_stack: list[str]
    roles: list[str] = Field(default_factory=list)
    experience_months: int = Field(default=0, ge=0)


class CompanySummary(DTO):
    company_id: UUID
    name: str
    contact: str


class FspEvidence(DTO):
    status: Literal["not_linked", "linked_empty", "linked_with_data", "unavailable"]
    signal: float = Field(default=0, ge=0, le=100)
    source: Literal["demo", "registry"] = "demo"
    fetched_at: datetime | None = None


class CandidateContacts(DTO):
    candidate_id: UUID
    email: str | None = None
    phone: str | None = None


class InvitationStatus(StrEnum):
    SENT = "sent"
    VIEWED = "viewed"
    ACCEPTED = "accepted"
    DECLINED = "declined"


Specialization = Literal["backend", "qa"]
Grade = Literal["junior", "middle", "senior"]


class SurveyCreate(DTO):
    industry: Annotated[str, Field(min_length=2, max_length=80)]
    specialization: Specialization
    declared_grade: Grade
    roles: Annotated[
        list[Annotated[str, Field(min_length=2, max_length=60)]], Field(min_length=1, max_length=8)
    ]
    experience_months: Annotated[int, Field(ge=0, le=720)]


class SurveyResponse(SurveyCreate):
    id: UUID
    catalog_version: str
    created_at: AwareDatetime


class SurveyHistory(DTO):
    items: list[SurveyResponse]


class AssessmentStart(DTO):
    specialization: Specialization
    target_grade: Grade


class AssessmentAnswerUpdate(DTO):
    answers: dict[str, dict[str, Any]]


class AssessmentQuestion(DTO):
    name: str
    label: str
    kind: Literal["choice", "multi", "number"]
    choices: list[dict[str, str]] = Field(default_factory=list)


class AssessmentItemPublic(DTO):
    id: UUID
    position: int
    family: str
    title: str
    scenario: str
    questions: list[AssessmentQuestion]
    answers: dict[str, Any] = Field(default_factory=dict)


class AssessmentResult(DTO):
    id: UUID
    specialization: Specialization
    target_grade: Grade
    status: Literal["in_progress", "passed", "failed", "expired"]
    started_at: AwareDatetime
    deadline_at: AwareDatetime
    submitted_at: AwareDatetime | None = None
    score: float | None = Field(default=None, ge=0, le=100)
    family_scores: dict[str, float] | None = None
    passed: bool | None = None
    next_grade_recommended: bool | None = None
    items: list[AssessmentItemPublic] = Field(default_factory=list)


class AssessmentHistoryItem(DTO):
    id: UUID
    specialization: Specialization
    target_grade: Grade
    status: Literal["in_progress", "passed", "failed", "expired"]
    started_at: AwareDatetime
    deadline_at: AwareDatetime
    submitted_at: AwareDatetime | None = None
    score: float | None = Field(default=None, ge=0, le=100)
    passed: bool | None = None
    next_grade_recommended: bool | None = None


class AssessmentHistory(DTO):
    items: list[AssessmentHistoryItem]


class CategoryConfirm(DTO):
    assessment_id: UUID


class CategoryState(DTO):
    verified: VerifiedCategory | None = None
    provisional: AssessmentHistoryItem | None = None


class CategoryHistoryItem(DTO):
    assessment_id: UUID
    category_code: str
    assigned_at: AwareDatetime
    next_change_at: AwareDatetime


class CategoryHistory(DTO):
    items: list[CategoryHistoryItem]


class PilotJoin(DTO):
    invite_code: Annotated[str, Field(min_length=16, max_length=128)]


class PilotAttemptPublic(DTO):
    id: UUID
    form_code: Literal["A", "B"]
    sequence: Literal[1, 2]
    status: Literal["in_progress", "awaiting_manual_review", "reviewed", "expired"]
    started_at: AwareDatetime
    deadline_at: AwareDatetime
    submitted_at: AwareDatetime | None = None
    items: list[AssessmentItemPublic] = Field(default_factory=list)


class PilotProgress(DTO):
    form_code: Literal["A", "B"]
    sequence: Literal[1, 2]
    status: Literal["in_progress", "awaiting_manual_review", "reviewed", "expired"]
    submitted_at: AwareDatetime | None = None


class PilotState(DTO):
    enrolled: bool
    participant_code: str | None = None
    specialization: Specialization | None = None
    target_grade: Grade | None = None
    form_order: Literal["A-first", "B-first"] | None = None
    manual_review_ready: bool = False
    attempts: list[PilotProgress] = Field(default_factory=list)
    current_attempt: PilotAttemptPublic | None = None
