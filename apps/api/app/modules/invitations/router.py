from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Request
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.contracts.schemas import ActorContext, CandidateContacts, CandidatePublic, Role
from app.core.db import get_db
from app.core.errors import ERROR_RESPONSES, AppError
from app.core.rate_limit import rate_limit
from app.core.security import Actor, require_role
from app.modules.invitations.models import InvitationEvent
from app.modules.invitations.schemas import (
    EmployerInvitationContext,
    InvitationCreate,
    InvitationDecision,
    InvitationEventResponse,
    InvitationHistory,
    InvitationListResponse,
    InvitationResponse,
)
from app.modules.invitations.service import ContactService, InvitationService
from app.modules.profiles.dependencies import make_public_read, port
from app.modules.profiles.privacy import aware
from app.modules.profiles.schemas import PublicProfileList

router = APIRouter(tags=["Invitations"], responses=ERROR_RESPONSES)
DB = Annotated[Session, Depends(get_db)]
Candidate = Annotated[ActorContext, Depends(require_role(Role.CANDIDATE))]
Employer = Annotated[ActorContext, Depends(require_role(Role.EMPLOYER))]


def invitation_service(request: Request, db: DB):
    return InvitationService(
        db, make_public_read(request.app, db), port(request.app, "company_read", db)
    )


Service = Annotated[InvitationService, Depends(invitation_service)]


def party(actor: Actor, service: Service):
    if not actor.email_verified:
        raise AppError(403, "EMAIL_NOT_VERIFIED", "Подтвердите email")
    if actor.role == Role.EMPLOYER:
        service.company(actor)
    return actor


Party = Annotated[ActorContext, Depends(party)]


@router.get("/employer/invitation-context", response_model=EmployerInvitationContext)
def context(actor: Employer, service: Service):
    company = service.company(actor)
    return EmployerInvitationContext(
        company_id=company.company_id, company_name=company.name, company_contact=company.contact
    )


@router.get("/employer/candidates", response_model=PublicProfileList)
def candidates(
    actor: Employer,
    service: Service,
    cursor: UUID | None = None,
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
):
    service.company(actor)
    rows = service.profiles.list_public(actor, after=cursor, limit=limit + 1)
    return PublicProfileList(
        items=rows[:limit],
        limit=limit,
        next_cursor=rows[limit - 1].candidate_id if len(rows) > limit else None,
    )


@router.get("/employer/candidates/{candidate_id}", response_model=CandidatePublic)
def candidate(candidate_id: UUID, actor: Employer, service: Service):
    service.company(actor)
    profile = service.profiles.get_public(candidate_id, actor)
    if profile is None:
        raise AppError(404, "NOT_FOUND", "Кандидат недоступен")
    return profile


@router.get("/employer/candidates/{candidate_id}/contacts", response_model=CandidateContacts)
def contacts(candidate_id: UUID, actor: Employer, service: Service, db: DB):
    service.company(actor)
    contact = ContactService(db).get(actor.company_id, candidate_id)
    if contact is None:
        raise AppError(404, "NOT_FOUND", "Контакты недоступны")
    return contact


@router.post("/invitations", response_model=InvitationResponse, status_code=201)
def create_invitation(
    payload: InvitationCreate,
    actor: Employer,
    request: Request,
    db: DB,
    service: Service,
    key: Annotated[
        str,
        Header(alias="Idempotency-Key", min_length=8, max_length=128, pattern=r"^[a-zA-Z0-9_-]+$"),
    ],
):
    service.company(actor)
    if service.existing(actor, key, payload) is None:
        rate_limit(request, "invitation:create", str(actor.company_id), limit=30, seconds=3600)
    try:
        row = service.create(actor, payload, key, request.state.request_id)
        db.commit()
    except IntegrityError:
        db.rollback()
        row = service.existing(actor, key, payload)
        if row is None:
            raise AppError(
                409,
                "ACTIVE_INVITATION_EXISTS",
                "У этой компании уже есть активное предложение кандидату",
            ) from None
    except Exception:
        db.rollback()
        raise
    return service.response(row)


@router.get("/invitations", response_model=InvitationListResponse)
def invitations(
    actor: Party,
    service: Service,
    cursor: UUID | None = None,
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
):
    return service.list(actor, cursor, limit)


@router.get("/invitations/{invitation_id}", response_model=InvitationResponse)
def invitation(invitation_id: UUID, actor: Party, service: Service):
    return service.response(service.owned(invitation_id, actor))


@router.get("/invitations/{invitation_id}/events", response_model=InvitationHistory)
def history(invitation_id: UUID, actor: Party, service: Service, db: DB):
    row = service.owned(invitation_id, actor)
    events = db.scalars(
        select(InvitationEvent)
        .where(InvitationEvent.invitation_id == row.id)
        .order_by(InvitationEvent.created_at, InvitationEvent.id)
    ).all()
    return InvitationHistory(
        items=[
            InvitationEventResponse(
                old_status=event.old_status,
                new_status=event.new_status,
                created_at=aware(event.created_at),
            )
            for event in events
        ]
    )


@router.post("/invitations/{invitation_id}/view", response_model=InvitationResponse)
def view(invitation_id: UUID, actor: Candidate, request: Request, db: DB, service: Service):
    try:
        row = service.view(invitation_id, actor, request.state.request_id)
        db.commit()
    except Exception:
        db.rollback()
        raise
    return service.response(row)


@router.post("/invitations/{invitation_id}/decision", response_model=InvitationResponse)
def decision(
    invitation_id: UUID,
    payload: InvitationDecision,
    actor: Candidate,
    request: Request,
    db: DB,
    service: Service,
):
    try:
        row = service.decision(invitation_id, actor, payload, request.state.request_id)
        db.commit()
    except Exception:
        db.rollback()
        raise
    return service.response(row)
