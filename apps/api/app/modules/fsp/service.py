from uuid import UUID

from sqlalchemy.orm import Session

from app.contracts.schemas import FspEvidence
from app.core.db import utcnow
from app.core.errors import AppError
from app.core.models import User
from app.modules.fsp.models import FspLink
from app.modules.fsp.provider import FspRegistry
from app.modules.fsp.schemas import FspSelf


class SqlAlchemyFspRead:
    def __init__(self, db: Session, registry: FspRegistry):
        self.db, self.registry = db, registry

    def get_evidence(self, candidate_id: UUID) -> FspEvidence:
        link = self.db.get(FspLink, str(candidate_id))
        if link is None:
            return FspEvidence(status="not_linked")
        user = self.db.get(User, str(candidate_id))
        try:
            if user is None or not user.email_verified:
                raise AppError(503, "FSP_UNAVAILABLE", "Связь с реестром недоступна")
            identity = self.registry.verify_owner(link.fsp_id, candidate_id, user.email)
        except (ConnectionError, TimeoutError):
            return FspEvidence(status="unavailable", fsp_id=link.fsp_id)
        except AppError as exc:
            if exc.status not in {422, 503}:
                raise
            return FspEvidence(status="unavailable", fsp_id=link.fsp_id)
        return FspEvidence(
            status="linked_with_data" if identity.achievements else "linked_empty",
            signal=identity.signal,
            source=identity.source,
            fetched_at=utcnow(),
            fsp_id=link.fsp_id,
            achievements=identity.achievements,
        )

    def get_self(self, candidate_id: UUID, verified_email: str) -> FspSelf:
        evidence = self.get_evidence(candidate_id)
        try:
            available = self.registry.owned_identity(candidate_id, verified_email).fsp_id
        except (ConnectionError, TimeoutError):
            return FspSelf(
                **{
                    **evidence.model_dump(),
                    "status": "unavailable",
                    "signal": 0,
                    "achievements": [],
                }
            )
        except AppError as exc:
            if exc.status != 503:
                raise
            return FspSelf(
                **{
                    **evidence.model_dump(),
                    "status": "unavailable",
                    "signal": 0,
                    "achievements": [],
                }
            )
        return FspSelf(**evidence.model_dump(), available_fsp_id=available)
