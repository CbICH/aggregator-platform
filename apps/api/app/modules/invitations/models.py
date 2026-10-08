"""Invitation history and contact grants issued by an explicit acceptance.

company/need/vacancy IDs remain external references until C owns their tables.
"""

from datetime import datetime

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, new_id, utcnow


class Invitation(Base):
    __tablename__ = "invitations"
    __table_args__ = (
        CheckConstraint(
            "status IN ('sent', 'viewed', 'accepted', 'declined')", name="ck_invitation_status"
        ),
        CheckConstraint("salary_min > 0 AND salary_max >= salary_min", name="ck_invitation_salary"),
        CheckConstraint(
            "salary_currency = 'RUB' AND salary_period = 'month' AND salary_tax_basis = 'gross'",
            name="ck_invitation_salary_units",
        ),
        CheckConstraint("version >= 1", name="ck_invitation_version"),
        UniqueConstraint("company_id", "idempotency_key", name="uq_invitation_request"),
        Index(
            "uq_invitation_active",
            "company_id",
            "candidate_id",
            unique=True,
            postgresql_where=text("status IN ('sent', 'viewed')"),
            sqlite_where=text("status IN ('sent', 'viewed')"),
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    candidate_id: Mapped[str] = mapped_column(
        ForeignKey("candidate_profiles.candidate_id", ondelete="CASCADE"), index=True
    )
    company_id: Mapped[str] = mapped_column(String(36), index=True)
    need_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    vacancy_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    company_name: Mapped[str] = mapped_column(String(200))
    candidate_alias: Mapped[str] = mapped_column(
        String(40), default="Кандидат", server_default="Кандидат"
    )
    category_snapshot: Mapped[dict] = mapped_column(JSON, default=dict, server_default="{}")
    description: Mapped[str] = mapped_column(Text)
    company_contact: Mapped[str] = mapped_column(String(300))
    salary_min: Mapped[int] = mapped_column(Integer)
    salary_max: Mapped[int] = mapped_column(Integer)
    salary_currency: Mapped[str] = mapped_column(String(3), default="RUB")
    salary_period: Mapped[str] = mapped_column(String(10), default="month")
    salary_tax_basis: Mapped[str] = mapped_column(String(10), default="gross")
    evidence_snapshot: Mapped[list[dict]] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(16), default="sent", index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    idempotency_key: Mapped[str] = mapped_column(String(128))
    payload_hash: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    viewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class InvitationEvent(Base):
    __tablename__ = "invitation_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    invitation_id: Mapped[str] = mapped_column(
        ForeignKey("invitations.id", ondelete="CASCADE"), index=True
    )
    actor_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    old_status: Mapped[str | None] = mapped_column(String(16), nullable=True)
    new_status: Mapped[str] = mapped_column(String(16))
    request_id: Mapped[str] = mapped_column(String(36))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ContactGrant(Base):
    __tablename__ = "contact_grants"
    __table_args__ = (
        Index("ix_grants_company_candidate", "company_id", "candidate_id"),
        CheckConstraint(
            "(source_kind = 'invitation' AND invitation_id IS NOT NULL AND application_id IS NULL) OR (source_kind = 'application' AND application_id IS NOT NULL AND invitation_id IS NULL)",
            name="ck_contact_grant_source",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    company_id: Mapped[str] = mapped_column(String(36), index=True)
    candidate_id: Mapped[str] = mapped_column(
        ForeignKey("candidate_profiles.candidate_id", ondelete="CASCADE"), index=True
    )
    source_kind: Mapped[str] = mapped_column(String(16))
    invitation_id: Mapped[str | None] = mapped_column(
        ForeignKey("invitations.id", ondelete="CASCADE"), nullable=True, unique=True
    )
    application_id: Mapped[str | None] = mapped_column(String(36), nullable=True, unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
