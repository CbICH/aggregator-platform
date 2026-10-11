from datetime import UTC
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.contracts.ports import AssessmentRead, FspRead
from app.contracts.schemas import FspEvidence
from app.core.db import utcnow
from app.core.errors import AppError
from app.core.models import AuditEvent
from app.modules.profiles.models import (
    CandidateContact,
    CandidateProfile,
    ProfileConsent,
    VisibilitySettings,
)
from app.modules.profiles.schemas import (
    CandidateSelf,
    ProfileContactDetails,
    ProfilePatch,
)

PROCESSING_VERSION = "profile-processing-v1"
PROCESSING_TEXT = (
    "Я согласен на хранение и обработку ФИО, контактных данных, ролей, стажа, "
    "технологий, софт-скиллов и текста резюме для ведения моего профиля в ФСП Сигнал. "
    "Это согласие не разрешает публикацию профиля или передачу контактов работодателям."
)


class ProfileService:
    """Services share the request session; the router owns commit/rollback."""

    def __init__(
        self, db: Session, assessments: AssessmentRead | None = None, fsp: FspRead | None = None
    ):
        self.db = db
        self.assessments = assessments
        self.fsp = fsp

    def has_processing_consent(self, candidate_id: str) -> bool:
        return (
            self.db.scalar(
                select(ProfileConsent.id)
                .where(
                    ProfileConsent.candidate_id == candidate_id,
                    ProfileConsent.consent_type == "profile_processing",
                    ProfileConsent.version == PROCESSING_VERSION,
                    ProfileConsent.revoked_at.is_(None),
                )
                .limit(1)
            )
            is not None
        )

    def fsp_evidence(self, candidate_id: UUID) -> FspEvidence:
        if self.fsp is None:
            return FspEvidence(status="unavailable")
        try:
            return self.fsp.get_evidence(candidate_id)
        except (ConnectionError, TimeoutError):
            return FspEvidence(status="unavailable")
        except AppError as exc:
            if exc.status == 503:
                return FspEvidence(status="unavailable")
            raise

    def get_self(self, candidate_id: UUID, account_email: str) -> CandidateSelf:
        from app.modules.profiles.privacy import PrivacyService

        key = str(candidate_id)
        profile = self.db.get(CandidateProfile, key)
        contact = self.db.get(CandidateContact, key) if profile else None
        contacts = ProfileContactDetails(
            email=contact.email if contact else account_email,
            phone=contact.phone if contact else None,
            contact_method=contact.contact_method if contact else "",
        )
        complete = bool(
            profile
            and profile.full_name
            and profile.roles
            and profile.declared_stack
            and (contacts.email or contacts.phone)
        )
        updated = profile.updated_at if profile else None
        if updated and updated.tzinfo is None:
            updated = updated.replace(tzinfo=UTC)
        return CandidateSelf(
            candidate_id=candidate_id,
            saved=profile is not None,
            version=profile.version if profile else 0,
            full_name=profile.full_name if profile else "",
            alias=profile.alias if profile else f"Кандидат {key[:8]}",
            roles=profile.roles if profile else [],
            experience_months=profile.experience_months if profile else 0,
            declared_stack=profile.declared_stack if profile else [],
            soft_skills=profile.soft_skills if profile else [],
            resume_text=profile.resume_text if profile else "",
            contacts=contacts,
            profile_complete=complete,
            processing_consent_active=self.has_processing_consent(key) if profile else False,
            verified_category=PrivacyService(self.db, self.assessments).verified(candidate_id),
            privacy=PrivacyService(self.db, self.assessments).state(candidate_id),
            fsp=self.fsp_evidence(candidate_id),
            updated_at=updated,
        )

    def save(self, candidate_id: UUID, account_email: str, payload: ProfilePatch, request_id: str):
        key = str(candidate_id)
        profile = self.db.get(CandidateProfile, key)
        if (
            payload.processing_consent_version is not None
            and payload.processing_consent_version != PROCESSING_VERSION
        ):
            raise AppError(409, "CONSENT_VERSION_OUTDATED", "Обновите условия обработки профиля")
        consent_active = bool(profile and self.has_processing_consent(key))
        if not consent_active and payload.processing_consent_accepted is not True:
            raise AppError(
                422,
                "PROFILE_CONSENT_REQUIRED",
                "Для сохранения профиля примите условия обработки данных",
                {"processing_consent_accepted": "Требуется согласие"},
            )
        changes = payload.model_dump(
            exclude_unset=True,
            exclude={
                "contacts",
                "expected_version",
                "processing_consent_accepted",
                "processing_consent_version",
            },
        )
        now = utcnow()
        if profile is None:
            if payload.expected_version != 0:
                raise AppError(
                    409, "PROFILE_VERSION_CONFLICT", "Профиль изменился. Обновите страницу"
                )
            profile = CandidateProfile(candidate_id=key, alias=f"Кандидат {key[:8]}", **changes)
            self.db.add(profile)
            self.db.flush()
            contact = CandidateContact(candidate_id=key, email=account_email)
            self.db.add(contact)
            self.db.add(VisibilitySettings(candidate_id=key))
        else:
            changed_id = self.db.scalar(
                update(CandidateProfile)
                .where(
                    CandidateProfile.candidate_id == key,
                    CandidateProfile.version == payload.expected_version,
                )
                .values(**changes, version=CandidateProfile.version + 1, updated_at=now)
                .returning(CandidateProfile.candidate_id)
            )
            if changed_id is None:
                raise AppError(
                    409,
                    "PROFILE_VERSION_CONFLICT",
                    "Профиль изменился в другой вкладке. Обновите страницу",
                )
            contact = self.db.get(CandidateContact, key)
            if contact is None:
                contact = CandidateContact(candidate_id=key, email=account_email)
                self.db.add(contact)
        if payload.contacts is not None:
            for name, value in payload.contacts.model_dump(exclude_unset=True).items():
                setattr(contact, name, value)
        if not consent_active:
            self.db.add(
                ProfileConsent(
                    candidate_id=key, consent_type="profile_processing", version=PROCESSING_VERSION
                )
            )
        self.db.add(
            AuditEvent(actor_id=key, action="profile.saved", object_id=key, request_id=request_id)
        )
        self.db.flush()
