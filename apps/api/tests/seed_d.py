"""Repeatable synthetic D seed, allowed only in an explicitly named test database."""

import json
from datetime import datetime, timedelta
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

from sqlalchemy import select
from sqlalchemy.engine import make_url

from app.core.models import RegistrationConsent, User
from app.core.security import password_hasher
from app.modules.invitations.models import ContactGrant, Invitation, InvitationEvent
from app.modules.profiles.models import (
    CandidateContact,
    CandidateProfile,
    ProfileConsent,
    VisibilitySettings,
)

PASSWORD = "correct horse battery"
FIXTURES = Path(__file__).resolve().parents[3] / "fixtures/profiles/scenarios.json"


def fixture_id(key):
    return str(uuid5(NAMESPACE_URL, f"fsp-signal:fixture:{key}"))


def seed(app, assessments, companies):
    database = make_url(app.state.settings.database_url).database or ""
    assert database.endswith("_test") or database.endswith("_test.db"), (
        "Synthetic seed requires a test database"
    )
    scenarios = json.loads(FIXTURES.read_text())
    fixed_time = datetime.fromisoformat(scenarios["fixed_time"])
    decision_time = fixed_time + timedelta(minutes=5)
    with app.state.session_factory.begin() as db:
        for item in scenarios["candidates"]:
            key = item["id"]
            if not db.get(User, key):
                db.add(
                    User(
                        id=key,
                        email=item["email"],
                        password_hash=password_hasher.hash(PASSWORD),
                        role="candidate",
                        email_verified=item["verified"],
                        created_at=fixed_time,
                    )
                )
                db.flush()
                db.add(
                    RegistrationConsent(
                        user_id=key, version="registration-v1", accepted_at=fixed_time
                    )
                )
                db.add(
                    CandidateProfile(
                        candidate_id=key,
                        alias="Кандидат " + item["scenario"],
                        full_name="Тестовый Кандидат " + item["scenario"],
                        roles=["backend"],
                        declared_stack=["python", "postgresql"],
                        experience_months=24,
                        created_at=fixed_time,
                        updated_at=fixed_time,
                        resume_text=(
                            "Работал над API и проверял качество.\n" * 220
                            if item["long_resume"]
                            else "Разрабатывал API и интеграции."
                        ),
                    )
                )
                db.flush()
                db.add(
                    CandidateContact(
                        candidate_id=key,
                        email=item["email"],
                        phone="+7 900 000-00-00",
                        contact_method="Email",
                    )
                )
                db.add(
                    VisibilitySettings(
                        candidate_id=key,
                        publication_enabled=item["publication"],
                        visible_fields=item["visible_fields"],
                        updated_at=fixed_time,
                    )
                )
                db.add(
                    ProfileConsent(
                        id=fixture_id(f"{key}:processing"),
                        candidate_id=key,
                        consent_type="profile_processing",
                        version="profile-processing-v1",
                        accepted_at=fixed_time,
                    )
                )
                if item["scenario"] == "D04" or item["publication"]:
                    db.add(
                        ProfileConsent(
                            id=fixture_id(f"{key}:publication"),
                            candidate_id=key,
                            consent_type="publication",
                            version="publication-v1",
                            accepted_at=fixed_time,
                            revoked_at=decision_time if item["scenario"] == "D04" else None,
                        )
                    )
            if item["category"]:
                assessments.verify(key)
        for item in scenarios["companies"]:
            if not db.get(User, item["user_id"]):
                db.add(
                    User(
                        id=item["user_id"],
                        email=item["email"],
                        password_hash=password_hasher.hash(PASSWORD),
                        role="employer",
                        email_verified=True,
                        company_id=item["id"],
                        created_at=fixed_time,
                    )
                )
                db.flush()
                db.add(
                    RegistrationConsent(
                        user_id=item["user_id"],
                        version="registration-v1",
                        accepted_at=fixed_time,
                    )
                )
            companies.add(item["id"], item["name"])
        db.flush()
        for item in scenarios["invitations"]:
            if db.get(Invitation, item["id"]):
                continue
            category = assessments.get_verified(item["candidate_id"])
            company = companies.get_summary(item["company_id"])
            profile = db.get(CandidateProfile, item["candidate_id"])
            row = Invitation(
                id=item["id"],
                candidate_id=item["candidate_id"],
                company_id=item["company_id"],
                candidate_alias=profile.alias,
                company_name=company.name,
                description="Синтетическое приглашение "
                + item["scenario"]
                + " для проверки состояний доступа.",
                company_contact="hr@example.com",
                salary_min=100000,
                salary_max=150000,
                idempotency_key="fixture-" + item["scenario"],
                payload_hash="0" * 64,
                status=item["status"],
                version=1 if item["status"] == "sent" else 2,
                category_snapshot={"category_code": category.category_code},
                evidence_snapshot=[],
                created_at=fixed_time,
                viewed_at=decision_time if item["status"] == "viewed" else None,
                decided_at=decision_time if item["status"] in {"accepted", "declined"} else None,
            )
            db.add(row)
            db.flush()
            db.add(
                InvitationEvent(
                    id=fixture_id(f"{row.id}:sent"),
                    invitation_id=row.id,
                    actor_id=item["actor_id"],
                    old_status=None,
                    new_status="sent",
                    request_id="fixture-seed",
                    created_at=fixed_time,
                )
            )
            if item["status"] != "sent":
                db.add(
                    InvitationEvent(
                        id=fixture_id(f"{row.id}:{item['status']}"),
                        invitation_id=row.id,
                        actor_id=item["candidate_id"],
                        old_status="sent",
                        new_status=item["status"],
                        request_id="fixture-seed",
                        created_at=decision_time,
                    )
                )
            if item["status"] == "accepted":
                db.add(
                    ContactGrant(
                        id=fixture_id(f"{row.id}:grant"),
                        candidate_id=row.candidate_id,
                        company_id=row.company_id,
                        source_kind="invitation",
                        invitation_id=row.id,
                        created_at=decision_time,
                    )
                )
                if not db.scalar(
                    select(ProfileConsent.id).where(
                        ProfileConsent.candidate_id == row.candidate_id,
                        ProfileConsent.consent_type == "contact_transfer",
                        ProfileConsent.revoked_at.is_(None),
                    )
                ):
                    db.add(
                        ProfileConsent(
                            id=fixture_id(f"{row.id}:contact-consent"),
                            candidate_id=row.candidate_id,
                            consent_type="contact_transfer",
                            version="contact-transfer-v1",
                            accepted_at=decision_time,
                        )
                    )
    return scenarios
