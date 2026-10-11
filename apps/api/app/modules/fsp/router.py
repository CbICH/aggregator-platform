from typing import Annotated

from fastapi import APIRouter, Depends, Request
from sqlalchemy import delete
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.contracts.schemas import ActorContext, Role
from app.core.db import get_db
from app.core.errors import ERROR_RESPONSES, AppError
from app.core.models import AuditEvent
from app.core.security import require_role
from app.modules.fsp.models import FspLink
from app.modules.fsp.schemas import FspLinkCommand, FspSelf
from app.modules.fsp.service import SqlAlchemyFspRead
from app.modules.profiles.privacy import PrivacyService

router = APIRouter(tags=["FSP"], responses=ERROR_RESPONSES)
Candidate = Annotated[ActorContext, Depends(require_role(Role.CANDIDATE))]
DB = Annotated[Session, Depends(get_db)]


def fsp_service(request: Request, db: DB) -> SqlAlchemyFspRead:
    return SqlAlchemyFspRead(db, request.app.state.fsp_registry)


Service = Annotated[SqlAlchemyFspRead, Depends(fsp_service)]


@router.get("/candidate/fsp", response_model=FspSelf)
def get_fsp(request: Request, actor: Candidate, service: Service):
    return service.get_self(actor.user_id, request.state.user.email)


@router.post("/candidate/fsp-link", response_model=FspSelf)
def link_fsp(payload: FspLinkCommand, request: Request, actor: Candidate, db: DB, service: Service):
    privacy = PrivacyService(db)
    if not privacy.active(str(actor.user_id), "profile_processing"):
        raise AppError(
            409, "PROFILE_PROCESSING_REQUIRED", "Сначала сохраните профиль с согласием на обработку"
        )
    privacy.lock_profile(actor.user_id)
    if not privacy.active(str(actor.user_id), "profile_processing"):
        raise AppError(409, "PROFILE_PROCESSING_REQUIRED", "Согласие на обработку отозвано")
    service.registry.verify_owner(payload.fsp_id, actor.user_id, request.state.user.email)
    existing = db.get(FspLink, str(actor.user_id))
    if existing and existing.fsp_id != payload.fsp_id:
        raise AppError(409, "FSP_ALREADY_LINKED", "Сначала отключите текущую связь")
    if existing is None:
        db.add(FspLink(candidate_id=str(actor.user_id), fsp_id=payload.fsp_id))
        db.add(
            AuditEvent(
                actor_id=str(actor.user_id),
                action="fsp.linked",
                object_id=str(actor.user_id),
                request_id=request.state.request_id,
            )
        )
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise AppError(409, "FSP_ALREADY_LINKED", "Этот ID уже связан с профилем") from None
    return service.get_self(actor.user_id, request.state.user.email)


@router.delete("/candidate/fsp-link", response_model=FspSelf)
def unlink_fsp(request: Request, actor: Candidate, db: DB, service: Service):
    deleted = db.execute(delete(FspLink).where(FspLink.candidate_id == str(actor.user_id))).rowcount
    if deleted:
        db.add(
            AuditEvent(
                actor_id=str(actor.user_id),
                action="fsp.unlinked",
                object_id=str(actor.user_id),
                request_id=request.state.request_id,
            )
        )
    db.commit()
    return service.get_self(actor.user_id, request.state.user.email)
