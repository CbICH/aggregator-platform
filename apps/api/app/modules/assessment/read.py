"""Read adapter for other modules that need an already verified category."""

from collections.abc import Callable
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.contracts.schemas import SkillEvidence, VerifiedCategory
from app.modules.assessment.models import SkillEvidenceRecord, VerifiedCategoryRecord


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def to_verified_category(db: Session, record: VerifiedCategoryRecord) -> VerifiedCategory:
    """Map persisted assessment data to the public cross-module contract."""
    evidence = db.scalars(
        select(SkillEvidenceRecord)
        .where(SkillEvidenceRecord.assessment_id == record.assessment_id)
        .order_by(SkillEvidenceRecord.skill_id)
    ).all()
    return VerifiedCategory(
        candidate_id=record.candidate_id,
        category_code=record.category_code,
        specialization=record.specialization,
        verified_grade=record.verified_grade,
        test_score=record.test_score,
        assessment_id=record.assessment_id,
        assessment_version=record.assessment_version,
        assigned_at=_aware(record.assigned_at),
        next_change_at=_aware(record.next_change_at),
        skills=[SkillEvidence(id=item.skill_id, score=item.score) for item in evidence],
    )


class SqlAlchemyAssessmentRead:
    """Implementation of ``AssessmentRead`` for C/D module composition."""

    def __init__(self, session_factory: Callable[[], Session] | Session):
        self._session_factory = session_factory

    def get_verified(self, candidate_id: UUID) -> VerifiedCategory | None:
        if isinstance(self._session_factory, Session):
            record = self._session_factory.get(VerifiedCategoryRecord, str(candidate_id))
            return to_verified_category(self._session_factory, record) if record else None
        with self._session_factory() as db:
            record = db.get(VerifiedCategoryRecord, str(candidate_id))
            return to_verified_category(db, record) if record else None
