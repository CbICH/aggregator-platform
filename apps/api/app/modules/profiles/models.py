"""D owns profile data; candidate_id is the candidate user's UUID."""

from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, new_id, utcnow


class CandidateProfile(Base):
    __tablename__ = "candidate_profiles"
    __table_args__ = (
        CheckConstraint(
            "experience_months >= 0 AND experience_months <= 1200", name="ck_profile_experience"
        ),
        CheckConstraint("version >= 1", name="ck_profile_version"),
    )

    candidate_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    full_name: Mapped[str] = mapped_column(String(200), default="")
    alias: Mapped[str] = mapped_column(String(40))
    roles: Mapped[list[str]] = mapped_column(JSON, default=list)
    experience_months: Mapped[int] = mapped_column(Integer, default=0)
    declared_stack: Mapped[list[str]] = mapped_column(JSON, default=list)
    soft_skills: Mapped[list[str]] = mapped_column(JSON, default=list)
    resume_text: Mapped[str] = mapped_column(Text, default="")
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class CandidateContact(Base):
    __tablename__ = "candidate_contacts"

    candidate_id: Mapped[str] = mapped_column(
        ForeignKey("candidate_profiles.candidate_id", ondelete="CASCADE"), primary_key=True
    )
    email: Mapped[str | None] = mapped_column(String(254), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(32), nullable=True)
    contact_method: Mapped[str] = mapped_column(String(200), default="")


class VisibilitySettings(Base):
    __tablename__ = "visibility_settings"

    candidate_id: Mapped[str] = mapped_column(
        ForeignKey("candidate_profiles.candidate_id", ondelete="CASCADE"), primary_key=True
    )
    publication_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    visible_fields: Mapped[list[str]] = mapped_column(
        JSON, default=lambda: ["roles", "declared_stack", "experience_months"]
    )
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ProfileConsent(Base):
    __tablename__ = "consents"
    __table_args__ = (
        Index("ix_consents_candidate_type", "candidate_id", "consent_type"),
        CheckConstraint(
            "consent_type IN ('profile_processing', 'publication', 'contact_transfer')",
            name="ck_consent_type",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    candidate_id: Mapped[str] = mapped_column(
        ForeignKey("candidate_profiles.candidate_id", ondelete="CASCADE"), index=True
    )
    consent_type: Mapped[str] = mapped_column(String(32))
    version: Mapped[str] = mapped_column(String(50))
    accepted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
