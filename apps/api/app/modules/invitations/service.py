import hashlib
import json
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.contracts.ports import CompanyRead
from app.contracts.schemas import ActorContext, CandidateContacts, Role, Salary
from app.core.db import utcnow
from app.core.errors import AppError
from app.core.models import AuditEvent
from app.modules.invitations.models import ContactGrant, Invitation, InvitationEvent
from app.modules.invitations.schemas import (
    InvitationCreate,
    InvitationDecision,
    InvitationEvidence,
    InvitationListResponse,
    InvitationResponse,
)
from app.modules.profiles.models import CandidateContact
from app.modules.profiles.privacy import CONTACT_VERSION, aware


def payload_hash(payload: InvitationCreate) -> str:
    data = payload.model_dump(mode="json")
    data["evidence_refs"] = sorted(data["evidence_refs"])
    return hashlib.sha256(
        json.dumps(data, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()
    ).hexdigest()


class ContactService:
    def __init__(self, db: Session):
        self.db = db

    def get(self, company_id: UUID, candidate_id: UUID) -> CandidateContacts | None:
        grant = self.db.scalar(
            select(ContactGrant.id)
            .join(Invitation, ContactGrant.invitation_id == Invitation.id)
            .where(
                ContactGrant.company_id == str(company_id),
                ContactGrant.candidate_id == str(candidate_id),
                ContactGrant.revoked_at.is_(None),
                Invitation.status == "accepted",
                Invitation.company_id == str(company_id),
                Invitation.candidate_id == str(candidate_id),
            )
            .limit(1)
        )
        if grant is None:
            return None
        contact = self.db.get(CandidateContact, str(candidate_id))
        if not contact:
            return None
        return CandidateContacts(
            candidate_id=candidate_id,
            email=contact.email,
            phone=contact.phone,
            contact_method=contact.contact_method,
        )


class InvitationService:
    def __init__(self, db, profiles, companies: CompanyRead | None):
        self.db, self.profiles, self.companies = db, profiles, companies
        self.privacy = profiles.privacy

    def company(self, actor: ActorContext):
        if actor.role != Role.EMPLOYER or not actor.email_verified:
            raise AppError(403, "ROLE_FORBIDDEN", "Действие недоступно")
        if actor.company_id is None:
            raise AppError(409, "COMPANY_REQUIRED", "Сначала заполните профиль компании")
        if self.companies is None:
            raise AppError(
                503, "COMPANY_SERVICE_UNAVAILABLE", "Данные компании временно недоступны"
            )
        summary = self.companies.get_summary(actor.company_id)
        if summary is None or summary.company_id != actor.company_id:
            raise AppError(404, "NOT_FOUND", "Компания недоступна")
        if not summary.name.strip() or len(summary.name) > 200:
            raise AppError(422, "COMPANY_INCOMPLETE", "Заполните название компании")
        return summary

    def owned(self, invitation_id: UUID, actor: ActorContext) -> Invitation:
        condition = (
            Invitation.candidate_id == str(actor.user_id)
            if actor.role == Role.CANDIDATE
            else Invitation.company_id == str(actor.company_id)
        )
        row = self.db.scalar(
            select(Invitation).where(Invitation.id == str(invitation_id), condition)
        )
        if row is None:
            raise AppError(404, "NOT_FOUND", "Предложение недоступно")
        return row

    def response(self, row: Invitation) -> InvitationResponse:
        active = (
            self.db.scalar(
                select(ContactGrant.id)
                .where(ContactGrant.invitation_id == row.id, ContactGrant.revoked_at.is_(None))
                .limit(1)
            )
            is not None
        )
        return InvitationResponse(
            invitation_id=row.id,
            candidate_id=row.candidate_id,
            candidate_alias=row.candidate_alias,
            company_id=row.company_id,
            company_name=row.company_name,
            need_id=row.need_id,
            vacancy_id=row.vacancy_id,
            description=row.description,
            salary=Salary(min=row.salary_min, max=row.salary_max),
            company_contact=row.company_contact,
            category_code=row.category_snapshot.get("category_code"),
            evidence=[InvitationEvidence(**item) for item in row.evidence_snapshot],
            status=row.status,
            version=row.version,
            created_at=aware(row.created_at),
            viewed_at=aware(row.viewed_at),
            decided_at=aware(row.decided_at),
            contact_access_active=active,
        )

    def existing(self, actor: ActorContext, key: str, payload: InvitationCreate):
        row = self.db.scalar(
            select(Invitation).where(
                Invitation.company_id == str(actor.company_id), Invitation.idempotency_key == key
            )
        )
        if row is not None and row.payload_hash != payload_hash(payload):
            raise AppError(
                409, "IDEMPOTENCY_CONFLICT", "Этот ключ уже использован для другого предложения"
            )
        return row

    def create(self, actor: ActorContext, payload: InvitationCreate, key: str, request_id: str):
        company = self.company(actor)
        existing = self.existing(actor, key, payload)
        if existing:
            return existing
        if not self.profiles.is_discoverable(payload.candidate_id):
            raise AppError(404, "NOT_FOUND", "Кандидат недоступен")
        # Serialize with publication withdrawal, profile writes and other creations.
        self.privacy.lock_profile(payload.candidate_id)
        existing = self.existing(actor, key, payload)
        if existing:
            return existing
        public = self.profiles.get_public(payload.candidate_id, actor)
        if public is None:
            raise AppError(404, "NOT_FOUND", "Кандидат недоступен")
        if payload.need_id and not self.companies.owns_need(actor.company_id, payload.need_id):
            raise AppError(404, "NOT_FOUND", "Потребность недоступна")
        if payload.vacancy_id:
            raise AppError(
                422, "VACANCY_NOT_SUPPORTED", "Предложение отправляется без привязки к вакансии"
            )
        verified = public.verified_category
        skills = {skill.id: skill for skill in verified.skills}
        if any(ref not in skills for ref in payload.evidence_refs):
            raise AppError(
                422,
                "EVIDENCE_INVALID",
                "Основания должны относиться к текущему подтверждению навыков",
            )
        row = Invitation(
            company_id=str(actor.company_id),
            candidate_id=str(payload.candidate_id),
            candidate_alias=public.display_name,
            company_name=company.name,
            need_id=str(payload.need_id) if payload.need_id else None,
            description=payload.description,
            company_contact=payload.company_contact,
            salary_min=payload.salary.min,
            salary_max=payload.salary.max,
            idempotency_key=key,
            payload_hash=payload_hash(payload),
            category_snapshot={
                "category_code": verified.category_code,
                "assessment_id": str(verified.assessment_id),
                "assessment_version": verified.assessment_version,
                "test_score": verified.test_score,
            },
            evidence_snapshot=[
                {
                    "skill_id": ref,
                    "score": skills[ref].score,
                    "assessment_id": str(verified.assessment_id),
                    "assessment_version": verified.assessment_version,
                }
                for ref in payload.evidence_refs
            ],
        )
        self.db.add(row)
        self.db.flush()
        self.event(row, actor, None, "sent", request_id)
        self.db.flush()
        return row

    def event(self, row, actor, old, new, request_id):
        self.db.add(
            InvitationEvent(
                invitation_id=row.id,
                actor_id=str(actor.user_id),
                old_status=old,
                new_status=new,
                request_id=request_id,
            )
        )
        self.db.add(
            AuditEvent(
                actor_id=str(actor.user_id),
                action=f"invitation.{new}",
                object_id=row.id,
                request_id=request_id,
            )
        )

    def view(self, invitation_id: UUID, actor: ActorContext, request_id: str):
        if actor.role != Role.CANDIDATE or not actor.email_verified:
            raise AppError(403, "ROLE_FORBIDDEN", "Действие недоступно")
        row = self.owned(invitation_id, actor)
        if row.status != "sent":
            return row
        changed = self.db.scalar(
            update(Invitation)
            .where(
                Invitation.id == row.id,
                Invitation.status == "sent",
                Invitation.version == row.version,
            )
            .values(status="viewed", viewed_at=utcnow(), version=Invitation.version + 1)
            .returning(Invitation.id)
        )
        if changed:
            self.event(row, actor, "sent", "viewed", request_id)
            self.db.flush()
        self.db.refresh(row)
        return row

    def decision(
        self, invitation_id: UUID, actor: ActorContext, payload: InvitationDecision, request_id: str
    ):
        if actor.role != Role.CANDIDATE or not actor.email_verified:
            raise AppError(403, "ROLE_FORBIDDEN", "Действие недоступно")
        row = self.owned(invitation_id, actor)
        target = "accepted" if payload.action == "accept" else "declined"
        # Lock order matches revocation: profile first, then invitation.
        self.privacy.lock_profile(UUID(row.candidate_id))
        self.db.refresh(row)
        if row.status in {"accepted", "declined"}:
            if row.status == target:
                return row  # Does not recreate a revoked grant.
            raise AppError(
                409, "INVITATION_FINAL", "По этому предложению уже принято другое решение"
            )
        if target == "accepted":
            if payload.contact_consent_version != CONTACT_VERSION:
                raise AppError(
                    409, "CONSENT_VERSION_OUTDATED", "Обновите условия передачи контактов"
                )
            if not self.privacy.active(row.candidate_id, "profile_processing"):
                raise AppError(
                    422,
                    "PROFILE_CONSENT_REQUIRED",
                    "Для передачи контактов примите условия обработки профиля",
                )
            contact = self.db.get(CandidateContact, row.candidate_id)
            if contact is None or not (contact.email or contact.phone):
                raise AppError(
                    422, "CONTACTS_REQUIRED", "Добавьте email или телефон в профиль перед принятием"
                )
        old = row.status
        changed = self.db.scalar(
            update(Invitation)
            .where(
                Invitation.id == row.id,
                Invitation.version == payload.expected_version,
                Invitation.status.in_(["sent", "viewed"]),
            )
            .values(status=target, version=Invitation.version + 1, decided_at=utcnow())
            .returning(Invitation.id)
        )
        if changed is None:
            raise AppError(
                409,
                "INVITATION_VERSION_CONFLICT",
                "Предложение изменилось. Загрузите актуальную версию",
            )
        if target == "accepted":
            self.privacy.record(UUID(row.candidate_id), "contact_transfer")
            self.db.add(
                ContactGrant(
                    company_id=row.company_id,
                    candidate_id=row.candidate_id,
                    source_kind="invitation",
                    invitation_id=row.id,
                )
            )
        self.event(row, actor, old, target, request_id)
        self.db.flush()
        self.db.refresh(row)
        return row

    def list(self, actor: ActorContext, after: UUID | None, limit: int):
        condition = (
            Invitation.candidate_id == str(actor.user_id)
            if actor.role == Role.CANDIDATE
            else Invitation.company_id == str(actor.company_id)
        )
        stmt = select(Invitation).where(condition)
        if after:
            stmt = stmt.where(Invitation.id > str(after))
        rows = self.db.scalars(stmt.order_by(Invitation.id).limit(limit + 1)).all()
        items = rows[:limit]
        return InvitationListResponse(
            items=[self.response(row) for row in items],
            next_cursor=items[-1].id if len(rows) > limit else None,
            limit=limit,
        )
