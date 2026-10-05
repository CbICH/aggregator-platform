from typing import Protocol
from uuid import UUID

from app.contracts.schemas import (
    ActorContext,
    CandidateContacts,
    CandidatePublic,
    CompanySummary,
    FspEvidence,
    VerifiedCategory,
)


class AssessmentRead(Protocol):
    def get_verified(self, candidate_id: UUID) -> VerifiedCategory | None: ...


class ProfileRead(Protocol):
    def get_public(self, candidate_id: UUID, actor: ActorContext) -> CandidatePublic | None: ...
    def is_discoverable(self, candidate_id: UUID) -> bool: ...


class CompanyRead(Protocol):
    def get_summary(self, company_id: UUID) -> CompanySummary | None: ...


class FspRead(Protocol):
    def get_evidence(self, candidate_id: UUID) -> FspEvidence: ...


class ContactAccess(Protocol):
    def get(self, company_id: UUID, candidate_id: UUID) -> CandidateContacts | None: ...


class ConsentWrite(Protocol):
    def record_registration(self, user_id: UUID, version: str) -> None: ...
