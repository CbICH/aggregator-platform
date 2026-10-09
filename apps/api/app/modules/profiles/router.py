from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.contracts.schemas import ActorContext, Role
from app.core.db import get_db
from app.core.errors import ERROR_RESPONSES, AppError
from app.core.security import require_role
from app.modules.profiles.dependencies import make_profile_service
from app.modules.profiles.privacy import PrivacyService
from app.modules.profiles.schemas import (
    CandidateSelf,
    ConsentCommand,
    PrivacyResponse,
    PrivacyUpdate,
    ProfilePatch,
    ProfileProcessingPolicy,
)
from app.modules.profiles.service import PROCESSING_TEXT, PROCESSING_VERSION, ProfileService

router = APIRouter(tags=["Profiles"], responses=ERROR_RESPONSES)
Candidate = Annotated[ActorContext, Depends(require_role(Role.CANDIDATE, verified=False))]
DB = Annotated[Session, Depends(get_db)]


def profile_service(request: Request, db: DB) -> ProfileService:
    # A/B can supply a request-scoped real implementation; fakes stay in tests.
    return make_profile_service(request.app, db)


Service = Annotated[ProfileService, Depends(profile_service)]
VerifiedCandidate = Annotated[ActorContext, Depends(require_role(Role.CANDIDATE))]


@router.get(
    "/candidate/profile.pdf",
    response_class=Response,
    responses={
        200: {
            "description": "Личный PDF-профиль",
            "content": {"application/pdf": {"schema": {"type": "string", "format": "binary"}}},
        }
    },
)
def profile_pdf(actor: VerifiedCandidate, request: Request, service: Service):
    from app.modules.profiles.pdf import render_profile

    profile = service.get_self(actor.user_id, request.state.user.email)
    if not profile.saved or not profile.processing_consent_active:
        raise AppError(422, "PROFILE_REQUIRED", "Сохраните профиль с согласием на обработку")
    return Response(
        render_profile(profile),
        media_type="application/pdf",
        headers={"Content-Disposition": 'attachment; filename="fsp-signal-profile.pdf"'},
    )


def privacy_service(service: Service, db: DB):
    return PrivacyService(db, service.assessments)


Privacy = Annotated[PrivacyService, Depends(privacy_service)]


@router.get("/candidate/privacy", response_model=PrivacyResponse)
def own_privacy(actor: Candidate, service: Privacy):
    return service.get(actor.user_id)


@router.patch("/candidate/privacy", response_model=PrivacyResponse)
def change_privacy(
    payload: PrivacyUpdate, actor: VerifiedCandidate, request: Request, db: DB, service: Privacy
):
    try:
        service.change(actor.user_id, payload, request.state.request_id)
        db.commit()
    except Exception:
        db.rollback()
        raise
    return service.get(actor.user_id)


@router.post("/candidate/consents", response_model=PrivacyResponse)
def change_consent(
    payload: ConsentCommand, actor: VerifiedCandidate, request: Request, db: DB, service: Privacy
):
    try:
        service.consent(actor.user_id, payload, request.state.request_id)
        db.commit()
    except Exception:
        db.rollback()
        raise
    return service.get(actor.user_id)


@router.get("/candidate/profile-policy", response_model=ProfileProcessingPolicy)
def processing_policy(actor: Candidate):
    return ProfileProcessingPolicy(version=PROCESSING_VERSION, text=PROCESSING_TEXT)


@router.get("/candidate/profile", response_model=CandidateSelf)
def own_profile(actor: Candidate, request: Request, service: Service):
    """Read only the authenticated candidate's draft. GET never creates rows."""
    return service.get_self(actor.user_id, request.state.user.email)


@router.patch("/candidate/profile", response_model=CandidateSelf)
def save_profile(
    payload: ProfilePatch, actor: Candidate, request: Request, db: DB, service: Service
):
    """Save a private profile. Category, publication and ownership are read-only."""
    try:
        service.save(actor.user_id, request.state.user.email, payload, request.state.request_id)
        db.commit()
    except IntegrityError:
        db.rollback()
        raise AppError(
            409, "PROFILE_VERSION_CONFLICT", "Профиль изменился. Обновите страницу"
        ) from None
    except Exception:
        db.rollback()
        raise
    return service.get_self(actor.user_id, request.state.user.email)
