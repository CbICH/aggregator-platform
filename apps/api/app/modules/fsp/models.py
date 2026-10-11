"""Only the association is persisted; registry results belong to its adapter."""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, utcnow


class FspLink(Base):
    __tablename__ = "fsp_links"

    candidate_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    fsp_id: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    linked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
