"""Matching C: companies owned by employers.

Один работодатель владеет ровно одной компанией. При создании компании её id
записывается в users.company_id (поле уже существует в core-миграции A),
чтобы ActorContext.company_id был доступен в последующих запросах.
"""

from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, new_id, utcnow


class Company(Base):
    __tablename__ = "companies"
    __table_args__ = (
        UniqueConstraint("owner_user_id"),
        Index("ix_companies_owner_user_id", "owner_user_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    owner_user_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="CASCADE"),
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    industry: Mapped[str] = mapped_column(String(40), nullable=False)
    city: Mapped[str] = mapped_column(String(80), nullable=False)
    contact_name: Mapped[str] = mapped_column(String(120), nullable=False)
    contact_role: Mapped[str | None] = mapped_column(String(80), nullable=True)
    contact_email: Mapped[str] = mapped_column(String(254), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )


class EmployerNeed(Base):
    """Потребность компании: что ищет работодатель.

    JSON-поля хранят массивы технологий, грейдов и проверяемых навыков.
    """

    __tablename__ = "employer_needs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    company_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("companies.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    title: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    specialization: Mapped[str] = mapped_column(String(16), nullable=False)
    grades: Mapped[list] = mapped_column(JSON, nullable=False)
    declared_stack: Mapped[list] = mapped_column(JSON, nullable=False)
    required_skills: Mapped[list] = mapped_column(JSON, nullable=False)
    work_format: Mapped[str] = mapped_column(String(16), nullable=False)
    salary_min: Mapped[int | None] = mapped_column(nullable=True)
    salary_max: Mapped[int | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )


class SearchSnapshot(Base):
    """Stores query and membership, never candidate resume/contact/hidden fields."""

    __tablename__ = "search_snapshots"
    __table_args__ = (Index("ix_search_snapshots_company_created", "company_id", "created_at"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    company_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False
    )
    filters: Mapped[dict] = mapped_column(JSON, nullable=False)
    need_snapshot: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    candidate_ids: Mapped[list] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
