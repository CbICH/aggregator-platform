"""Live visibility and consent decisions; never exposes resume/contact fields."""

from datetime import UTC
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.contracts.ports import AssessmentRead
from app.contracts.schemas import ActorContext, CandidatePublic, Role
from app.core.db import utcnow
from app.core.errors import AppError
from app.core.models import AuditEvent, User
from app.modules.invitations.models import ContactGrant
from app.modules.profiles.models import (
    CandidateContact,
    CandidateProfile,
    ProfileConsent,
    VisibilitySettings,
)
from app.modules.profiles.schemas import (
    ConsentCommand,
    ConsentReceipt,
    PrivacyResponse,
    PrivacyUpdate,
    ProfilePrivacy,
    ProfileProcessingPolicy,
)
from app.modules.profiles.service import PROCESSING_VERSION

PUBLICATION_VERSION = "publication-v1"
CONTACT_VERSION = "contact-transfer-v1"
PUBLICATION_TEXT = "Разрешаю показывать работодателям псевдоним, подтверждённые навыки и выбранные поля профиля. ФИО, резюме и контакты остаются приватными. Публикацию можно отозвать."
CONTACT_TEXT = "Принимая предложение, разрешаю этой компании получать мои контактные данные. Доступ можно отозвать в настройках приватности; уже полученные компанией данные отозвать технически невозможно."
VERSIONS = {
    "publication": PUBLICATION_VERSION,
    "contact_transfer": CONTACT_VERSION,
    "profile_processing": PROCESSING_VERSION,
}
PUBLIC_FIELDS = {"roles", "declared_stack", "experience_months"}
PUBLIC_STACK = frozenset(
    {
        "python",
        "postgresql",
        "javascript",
        "typescript",
        "java",
        "kotlin",
        "go",
        "rust",
        "c",
        "c++",
        "c#",
        ".net",
        "php",
        "ruby",
        "swift",
        "dart",
        "sql",
        "html",
        "css",
        "react",
        "vue",
        "angular",
        "node.js",
        "fastapi",
        "django",
        "flask",
        "spring",
        "git",
        "docker",
        "kubernetes",
        "linux",
        "redis",
        "mongodb",
        "mysql",
        "sqlite",
        "clickhouse",
        "kafka",
        "rabbitmq",
        "nginx",
        "terraform",
        "ansible",
        "jenkins",
        "pytest",
        "playwright",
        "selenium",
        "junit",
        "pandas",
        "numpy",
        "pytorch",
        "tensorflow",
        "aws",
        "azure",
        "gcp",
        "bash",
        "graphql",
        "rest",
        "grpc",
    }
)


def aware(value):
    return value.replace(tzinfo=UTC) if value and value.tzinfo is None else value


class PrivacyService:
    def __init__(self, db: Session, assessments: AssessmentRead | None = None):
        self.db, self.assessments = db, assessments

    def active(self, candidate_id: str, kind: str) -> bool:
        return (
            self.db.scalar(
                select(ProfileConsent.id)
                .where(
                    ProfileConsent.candidate_id == candidate_id,
                    ProfileConsent.consent_type == kind,
                    ProfileConsent.version == VERSIONS[kind],
                    ProfileConsent.revoked_at.is_(None),
                )
                .limit(1)
            )
            is not None
        )

    def verified(self, candidate_id: UUID):
        category = self.assessments.get_verified(candidate_id) if self.assessments else None
        return category if category and category.candidate_id == candidate_id else None

    def state(self, candidate_id: UUID) -> ProfilePrivacy:
        key = str(candidate_id)
        profile = self.db.get(CandidateProfile, key)
        contact = self.db.get(CandidateContact, key)
        user = self.db.get(User, key)
        visibility = self.db.get(VisibilitySettings, key)
        processing, publication = (
            self.active(key, "profile_processing"),
            self.active(key, "publication"),
        )
        checks = {
            "email_not_verified": bool(user and user.role == "candidate" and user.email_verified),
            "profile_incomplete": bool(
                profile
                and profile.full_name
                and profile.roles
                and profile.declared_stack
                and contact
                and (contact.email or contact.phone)
            ),
            "processing_consent_required": processing,
            "publication_consent_required": bool(
                publication and visibility and visibility.publication_enabled
            ),
            "category_not_verified": self.verified(candidate_id) is not None,
        }
        return ProfilePrivacy(
            publication_enabled=bool(visibility and visibility.publication_enabled),
            publication_consent_active=publication,
            processing_consent_active=processing,
            discoverable=all(checks.values()),
            blocked_reasons=[reason for reason, valid in checks.items() if not valid],
            visible_fields=visibility.visible_fields if visibility else [],
            version=profile.version if profile else 0,
        )

    def get(self, candidate_id: UUID) -> PrivacyResponse:
        rows = self.db.scalars(
            select(ProfileConsent)
            .where(ProfileConsent.candidate_id == str(candidate_id))
            .order_by(ProfileConsent.accepted_at, ProfileConsent.id)
        ).all()
        return PrivacyResponse(
            **self.state(candidate_id).model_dump(),
            consents=[
                ConsentReceipt(
                    consent_type=row.consent_type,
                    version=row.version,
                    accepted_at=aware(row.accepted_at),
                    revoked_at=aware(row.revoked_at),
                )
                for row in rows
            ],
            publication_policy=ProfileProcessingPolicy(
                version=PUBLICATION_VERSION, text=PUBLICATION_TEXT
            ),
            contact_policy=ProfileProcessingPolicy(version=CONTACT_VERSION, text=CONTACT_TEXT),
        )

    def lock_profile(self, candidate_id: UUID, expected_version: int | None = None):
        stmt = update(CandidateProfile).where(CandidateProfile.candidate_id == str(candidate_id))
        if expected_version is not None:
            stmt = stmt.where(CandidateProfile.version == expected_version).values(
                version=CandidateProfile.version + 1, updated_at=utcnow()
            )
        else:
            # Write lock works on PostgreSQL and SQLite, without changing the profile version.
            stmt = stmt.values(version=CandidateProfile.version)
        if self.db.scalar(stmt.returning(CandidateProfile.candidate_id)) is None:
            raise AppError(
                409, "PROFILE_VERSION_CONFLICT", "Профиль изменился. Загрузите актуальную версию"
            )
        self.db.expire_all()

    def record(self, candidate_id: UUID, kind: str):
        key = str(candidate_id)
        if not self.active(key, kind):
            self.db.add(ProfileConsent(candidate_id=key, consent_type=kind, version=VERSIONS[kind]))

    def revoke(self, candidate_id: UUID, kind: str):
        self.db.execute(
            update(ProfileConsent)
            .where(
                ProfileConsent.candidate_id == str(candidate_id),
                ProfileConsent.consent_type == kind,
                ProfileConsent.revoked_at.is_(None),
            )
            .values(revoked_at=utcnow())
        )

    def revoke_contacts(self, candidate_id: UUID):
        self.db.execute(
            update(ContactGrant)
            .where(
                ContactGrant.candidate_id == str(candidate_id), ContactGrant.revoked_at.is_(None)
            )
            .values(revoked_at=utcnow())
        )
        self.revoke(candidate_id, "contact_transfer")

    def change(self, candidate_id: UUID, payload: PrivacyUpdate, request_id: str):
        self.lock_profile(candidate_id, payload.expected_version)
        visibility = self.db.get(VisibilitySettings, str(candidate_id))
        if payload.publication_enabled is True:
            if payload.publication_consent_version != PUBLICATION_VERSION:
                raise AppError(409, "CONSENT_VERSION_OUTDATED", "Обновите условия публикации")
            blockers = set(self.state(candidate_id).blocked_reasons) - {
                "category_not_verified",
                "publication_consent_required",
            }
            if blockers:
                raise AppError(
                    422,
                    "PROFILE_NOT_READY",
                    "Подтвердите email, заполните профиль и примите условия обработки",
                )
            self.record(candidate_id, "publication")
            visibility.publication_enabled = True
        elif payload.publication_enabled is False:
            visibility.publication_enabled = False
            self.revoke(candidate_id, "publication")
        if payload.visible_fields is not None:
            visibility.visible_fields = payload.visible_fields
        if payload.revoke_contact_access:
            self.revoke_contacts(candidate_id)
        visibility.updated_at = utcnow()
        self.db.add(
            AuditEvent(
                actor_id=str(candidate_id),
                action="privacy.changed",
                object_id=str(candidate_id),
                request_id=request_id,
            )
        )
        self.db.flush()

    def consent(self, candidate_id: UUID, payload: ConsentCommand, request_id: str):
        if payload.version != VERSIONS[payload.consent_type]:
            raise AppError(409, "CONSENT_VERSION_OUTDATED", "Обновите условия согласия")
        if payload.consent_type == "publication":
            self.change(
                candidate_id,
                PrivacyUpdate(
                    expected_version=payload.expected_version,
                    publication_enabled=payload.action == "accept",
                    **(
                        {
                            "publication_consent_accepted": True,
                            "publication_consent_version": payload.version,
                        }
                        if payload.action == "accept"
                        else {}
                    ),
                ),
                request_id,
            )
            return
        if payload.action == "accept":
            raise AppError(
                422,
                "CONSENT_CONTEXT_REQUIRED",
                "Согласие на обработку принимается при сохранении профиля, на передачу контактов — при принятии конкретного предложения",
            )
        self.lock_profile(candidate_id, payload.expected_version)
        self.revoke_contacts(candidate_id)
        if payload.consent_type == "profile_processing":
            self.revoke(candidate_id, "profile_processing")
            self.revoke(candidate_id, "publication")
            visibility = self.db.get(VisibilitySettings, str(candidate_id))
            visibility.publication_enabled = False
            visibility.updated_at = utcnow()
        self.db.add(
            AuditEvent(
                actor_id=str(candidate_id),
                action="consent.revoked",
                object_id=str(candidate_id),
                request_id=request_id,
            )
        )
        self.db.flush()


class PublicProfileRead:
    def __init__(self, db: Session, assessments: AssessmentRead | None = None):
        self.db, self.assessments = db, assessments
        self.privacy = PrivacyService(db, assessments)

    def is_discoverable(self, candidate_id: UUID) -> bool:
        return self.privacy.state(candidate_id).discoverable

    def get_public(self, candidate_id: UUID, actor: ActorContext) -> CandidatePublic | None:
        if (
            actor.role != Role.EMPLOYER
            or not actor.email_verified
            or not actor.company_id
            or not self.is_discoverable(candidate_id)
        ):
            return None
        profile = self.db.get(CandidateProfile, str(candidate_id))
        category = self.privacy.verified(candidate_id)
        if category is None:
            return None
        fields = (
            set(self.db.get(VisibilitySettings, str(candidate_id)).visible_fields) & PUBLIC_FIELDS
        )
        # Unknown/free-form tags stay owner-only, including obfuscated contact strings.
        stack = [tag for tag in profile.declared_stack if tag in PUBLIC_STACK]
        return CandidatePublic(
            candidate_id=candidate_id,
            display_name=profile.alias,
            roles=profile.roles if "roles" in fields else None,
            declared_stack=stack if "declared_stack" in fields else None,
            experience_months=profile.experience_months if "experience_months" in fields else None,
            hidden_fields=sorted(PUBLIC_FIELDS - fields),
            verified_category=category,
        )

    def list_public(
        self, actor: ActorContext, *, after: UUID | None = None, limit: int = 20
    ) -> list[CandidatePublic]:
        if not 1 <= limit <= 51:
            raise ValueError("limit must be between 1 and 51")
        if actor.role != Role.EMPLOYER or not actor.email_verified or not actor.company_id:
            return []
        # B owns live category eligibility, so iterate bounded SQL batches until enough live profiles exist.
        cursor, items = str(after) if after else "", []
        while len(items) < limit:
            keys = self.db.scalars(
                select(CandidateProfile.candidate_id)
                .join(VisibilitySettings)
                .where(
                    CandidateProfile.candidate_id > cursor,
                    VisibilitySettings.publication_enabled.is_(True),
                )
                .order_by(CandidateProfile.candidate_id)
                .limit(100)
            ).all()
            if not keys:
                break
            for key in keys:
                cursor = key
                profile = self.get_public(UUID(key), actor)
                if profile:
                    items.append(profile)
                    if len(items) == limit:
                        break
        return items
