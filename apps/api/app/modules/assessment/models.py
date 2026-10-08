from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, new_id, utcnow


class Survey(Base):
    __tablename__ = "surveys"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    candidate_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    industry: Mapped[str] = mapped_column(String(80))
    specialization: Mapped[str] = mapped_column(String(32), index=True)
    declared_grade: Mapped[str] = mapped_column(String(16))
    roles: Mapped[list[str]] = mapped_column(JSON)
    experience_months: Mapped[int] = mapped_column(Integer)
    catalog_version: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AssessmentAttempt(Base):
    __tablename__ = "assessment_attempts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    candidate_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    survey_id: Mapped[str] = mapped_column(ForeignKey("surveys.id", ondelete="RESTRICT"))
    survey_snapshot: Mapped[dict] = mapped_column(JSON)
    specialization: Mapped[str] = mapped_column(String(32), index=True)
    target_grade: Mapped[str] = mapped_column(String(16), index=True)
    catalog_version: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(16), index=True, default="in_progress")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    deadline_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    score: Mapped[float | None] = mapped_column(Float, nullable=True)
    family_scores: Mapped[dict[str, float] | None] = mapped_column(JSON, nullable=True)
    passed: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    next_grade_recommended: Mapped[bool | None] = mapped_column(Boolean, nullable=True)

    __table_args__ = (
        Index(
            "uq_assessment_attempt_active_target",
            "candidate_id",
            "specialization",
            "target_grade",
            unique=True,
            sqlite_where=text("status = 'in_progress'"),
            postgresql_where=text("status = 'in_progress'"),
        ),
    )


class AssessmentItem(Base):
    __tablename__ = "assessment_items"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    attempt_id: Mapped[str] = mapped_column(
        ForeignKey("assessment_attempts.id", ondelete="CASCADE"), index=True
    )
    position: Mapped[int] = mapped_column(Integer)
    family: Mapped[str] = mapped_column(String(32))
    template_id: Mapped[str] = mapped_column(String(80))
    template_version: Mapped[str] = mapped_column(String(32))
    private_seed: Mapped[str] = mapped_column(String(64))
    prompt: Mapped[dict] = mapped_column(JSON)
    rubric: Mapped[list[dict]] = mapped_column(JSON)
    answers: Mapped[dict] = mapped_column(JSON, default=dict)
    score: Mapped[float | None] = mapped_column(Float, nullable=True)

    __table_args__ = (
        UniqueConstraint("attempt_id", "position", name="uq_assessment_item_position"),
    )


class VerifiedCategoryRecord(Base):
    __tablename__ = "verified_categories"

    candidate_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    category_code: Mapped[str] = mapped_column(String(64), index=True)
    specialization: Mapped[str] = mapped_column(String(32), index=True)
    verified_grade: Mapped[str] = mapped_column(String(16), index=True)
    test_score: Mapped[float] = mapped_column(Float)
    assessment_id: Mapped[str] = mapped_column(
        ForeignKey("assessment_attempts.id", ondelete="RESTRICT"), unique=True
    )
    assessment_version: Mapped[str] = mapped_column(String(80))
    assigned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    next_change_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class GradeHistory(Base):
    __tablename__ = "grade_history"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    candidate_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    assessment_id: Mapped[str] = mapped_column(
        ForeignKey("assessment_attempts.id", ondelete="RESTRICT")
    )
    category_code: Mapped[str] = mapped_column(String(64))
    assigned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    next_change_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        UniqueConstraint(
            "candidate_id", "assessment_id", name="uq_grade_history_candidate_assessment"
        ),
    )


class SkillEvidenceRecord(Base):
    __tablename__ = "skill_evidence"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    candidate_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    assessment_id: Mapped[str] = mapped_column(
        ForeignKey("assessment_attempts.id", ondelete="RESTRICT")
    )
    skill_id: Mapped[str] = mapped_column(String(80), index=True)
    score: Mapped[float] = mapped_column(Float)
    source: Mapped[str] = mapped_column(String(24), default="assessment")
    assessment_version: Mapped[str] = mapped_column(String(80))
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class PilotRun(Base):
    """A closed, invite-only A/B study. It never grants a public category."""

    __tablename__ = "pilot_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    invite_code_hash: Mapped[str] = mapped_column(String(64), unique=True)
    status: Mapped[str] = mapped_column(String(16), default="open", index=True)
    max_participants: Mapped[int] = mapped_column(Integer, default=8)
    specialization: Mapped[str] = mapped_column(String(32))
    target_grade: Mapped[str] = mapped_column(String(16))
    catalog_version: Mapped[str] = mapped_column(String(32))
    form_a_seed: Mapped[str] = mapped_column(String(64))
    form_b_seed: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class PilotEnrollment(Base):
    __tablename__ = "pilot_enrollments"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    run_id: Mapped[str] = mapped_column(ForeignKey("pilot_runs.id", ondelete="CASCADE"), index=True)
    candidate_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    participant_code: Mapped[str] = mapped_column(String(32), unique=True)
    form_order: Mapped[str] = mapped_column(String(8))
    manual_grade: Mapped[str | None] = mapped_column(String(16), nullable=True)
    manual_reviewer_count: Mapped[int] = mapped_column(Integer, default=0)
    manual_reviewed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    manual_review_resolution: Mapped[str | None] = mapped_column(String(500), nullable=True)
    joined_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    __table_args__ = (
        UniqueConstraint("run_id", "candidate_id", name="uq_pilot_enrollment_candidate"),
    )


class PilotManualReview(Base):
    """A private, immutable review recorded before a participant sees either form."""

    __tablename__ = "pilot_manual_reviews"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    enrollment_id: Mapped[str] = mapped_column(
        ForeignKey("pilot_enrollments.id", ondelete="CASCADE"), index=True
    )
    reviewer_code: Mapped[str] = mapped_column(String(64))
    assessed_grade: Mapped[str] = mapped_column(String(16))
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    __table_args__ = (
        UniqueConstraint("enrollment_id", "reviewer_code", name="uq_pilot_manual_review_reviewer"),
    )


class PilotAttempt(Base):
    __tablename__ = "pilot_attempts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    enrollment_id: Mapped[str] = mapped_column(
        ForeignKey("pilot_enrollments.id", ondelete="CASCADE"), index=True
    )
    form_code: Mapped[str] = mapped_column(String(1))
    sequence: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(32), default="in_progress", index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    deadline_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    score: Mapped[float | None] = mapped_column(Float, nullable=True)
    family_scores: Mapped[dict[str, float] | None] = mapped_column(JSON, nullable=True)
    passed: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    duration_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)

    __table_args__ = (
        UniqueConstraint("enrollment_id", "form_code", name="uq_pilot_attempt_form"),
        UniqueConstraint("enrollment_id", "sequence", name="uq_pilot_attempt_sequence"),
    )


class PilotItem(Base):
    __tablename__ = "pilot_items"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    attempt_id: Mapped[str] = mapped_column(
        ForeignKey("pilot_attempts.id", ondelete="CASCADE"), index=True
    )
    position: Mapped[int] = mapped_column(Integer)
    family: Mapped[str] = mapped_column(String(32))
    template_id: Mapped[str] = mapped_column(String(80))
    template_version: Mapped[str] = mapped_column(String(32))
    private_seed: Mapped[str] = mapped_column(String(64))
    prompt: Mapped[dict] = mapped_column(JSON)
    rubric: Mapped[list[dict]] = mapped_column(JSON)
    answers: Mapped[dict] = mapped_column(JSON, default=dict)
    score: Mapped[float | None] = mapped_column(Float, nullable=True)

    __table_args__ = (UniqueConstraint("attempt_id", "position", name="uq_pilot_item_position"),)
