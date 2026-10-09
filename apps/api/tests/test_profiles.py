from concurrent.futures import ThreadPoolExecutor
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.core.models import AuditEvent, User
from app.modules.invitations.models import ContactGrant, Invitation
from app.modules.profiles.models import (
    CandidateContact,
    CandidateProfile,
    ProfileConsent,
    VisibilitySettings,
)

PASSWORD = "correct horse battery"


def sign_in(client, register, email="candidate@example.com", role="candidate"):
    assert register(email=email, role=role).status_code == 202
    response = client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
    assert response.status_code == 200
    return response.json(), {"X-CSRF-Token": client.cookies.get("signal_csrf")}


def first_profile(**fields):
    return {
        "expected_version": 0,
        "processing_consent_accepted": True,
        "processing_consent_version": "profile-processing-v1",
        "full_name": " Иван Петров ",
        "roles": ["backend"],
        "declared_stack": ["Python", "PostgreSQL", "python"],
        "experience_months": 24,
        "soft_skills": ["Работа в команде"],
        "resume_text": "Создавал API заказов.",
        "contacts": {
            "email": "contact@example.com",
            "phone": "+7 900 000-00-00",
            "contact_method": "Email",
        },
        **fields,
    }


def test_get_draft_is_private_and_does_not_write(app, client, register):
    actor, _ = sign_in(client, register)
    result = client.get("/api/v1/candidate/profile")
    assert result.status_code == 200
    body = result.json()
    assert body["candidate_id"] == actor["id"]
    assert body["version"] == 0 and not body["saved"]
    assert body["contacts"]["email"] == actor["email"]
    assert not body["profile_complete"] and body["verified_category"] is None
    assert body["privacy"] == {
        "publication_enabled": False,
        "discoverable": False,
        "visible_fields": [],
        "publication_consent_active": False,
        "processing_consent_active": False,
        "version": 0,
        "blocked_reasons": [
            "email_not_verified",
            "profile_incomplete",
            "processing_consent_required",
            "publication_consent_required",
            "category_not_verified",
        ],
    }
    with app.state.session_factory() as db:
        assert db.scalar(select(func.count()).select_from(CandidateProfile)) == 0
        assert db.scalar(select(func.count()).select_from(ProfileConsent)) == 0


def test_save_profile_persists_separate_contacts_and_processing_receipt(app, client, register):
    actor, headers = sign_in(client, register)
    response = client.patch("/api/v1/candidate/profile", json=first_profile(), headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert body["full_name"] == "Иван Петров" and body["version"] == 1
    assert body["declared_stack"] == ["python", "postgresql"]
    assert body["processing_consent_active"] and body["profile_complete"]
    assert not body["privacy"]["publication_enabled"] and not body["privacy"]["discoverable"]
    assert body["updated_at"].endswith("Z") or body["updated_at"].endswith("+00:00")
    assert client.get("/api/v1/candidate/profile").json() == body
    assert client.get("/api/v1/me").json()["email"] == "candidate@example.com"
    with app.state.session_factory() as db:
        profile = db.get(CandidateProfile, actor["id"])
        assert profile.full_name == "Иван Петров" and not hasattr(profile, "email")
        assert db.get(CandidateContact, actor["id"]).email == "contact@example.com"
        assert not db.get(VisibilitySettings, actor["id"]).publication_enabled
        receipts = db.scalars(select(ProfileConsent)).all()
        assert len(receipts) == 1 and receipts[0].consent_type == "profile_processing"
        events = db.scalars(select(AuditEvent).where(AuditEvent.action == "profile.saved")).all()
        assert len(events) == 1 and events[0].object_id == actor["id"]


def test_partial_patch_preserves_fields_and_supports_contact_removal(app, client, register):
    _, headers = sign_in(client, register)
    assert (
        client.patch("/api/v1/candidate/profile", json=first_profile(), headers=headers).status_code
        == 200
    )
    response = client.patch(
        "/api/v1/candidate/profile",
        json={"expected_version": 1, "resume_text": "Новый опыт", "contacts": {"phone": None}},
        headers=headers,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["version"] == 2 and body["resume_text"] == "Новый опыт"
    assert body["full_name"] == "Иван Петров"
    assert body["contacts"] == {
        "email": "contact@example.com",
        "phone": None,
        "contact_method": "Email",
    }
    with app.state.session_factory() as db:
        assert db.scalar(select(func.count()).select_from(ProfileConsent)) == 1
    cleared = client.patch(
        "/api/v1/candidate/profile",
        json={"expected_version": 2, "contacts": {"email": None}},
        headers=headers,
    )
    assert cleared.status_code == 200 and not cleared.json()["profile_complete"]


@pytest.mark.parametrize(
    "payload, code",
    [
        ({"expected_version": 0, "full_name": "Иван"}, "PROFILE_CONSENT_REQUIRED"),
        (first_profile(processing_consent_version="old"), "CONSENT_VERSION_OUTDATED"),
    ],
)
def test_missing_or_old_consent_does_not_save(app, client, register, payload, code):
    _, headers = sign_in(client, register)
    response = client.patch("/api/v1/candidate/profile", json=payload, headers=headers)
    assert response.status_code in (409, 422) and response.json()["error"]["code"] == code
    with app.state.session_factory() as db:
        assert db.scalar(select(func.count()).select_from(CandidateProfile)) == 0
        assert db.scalar(select(func.count()).select_from(ProfileConsent)) == 0


@pytest.mark.parametrize(
    "change",
    [
        {"candidate_id": "10000000-0000-4000-8000-000000000001"},
        {"company_id": "10000000-0000-4000-8000-000000000001"},
        {"verified_category": {"verified_grade": "senior"}},
        {"privacy": {"publication_enabled": True}},
        {"experience_months": -1},
        {"experience_months": 1.5},
        {"experience_months": True},
        {"roles": ["arbitrary"]},
        {"roles": None},
        {"full_name": None},
        {"declared_stack": [" "]},
        {"resume_text": "x" * 12001},
        {"contacts": {"email": "not-email"}},
        {"contacts": {"phone": "       "}},
        {"contacts": {"phone": "+7 1234567890123456"}},
        {"contacts": {"contact_method": None}},
        {"contacts": {"candidate_id": "other"}},
        {"expected_version": True},
    ],
)
def test_invalid_or_privileged_fields_rejected_without_partial_write(app, client, register, change):
    _, headers = sign_in(client, register)
    response = client.patch(
        "/api/v1/candidate/profile", json=first_profile(**change), headers=headers
    )
    assert response.status_code == 422
    assert "contact@example.com" not in response.text
    with app.state.session_factory() as db:
        assert db.scalar(select(func.count()).select_from(CandidateProfile)) == 0


def test_profile_role_csrf_and_anonymous_guards(client, register):
    assert client.get("/api/v1/candidate/profile").status_code == 401
    assert client.patch("/api/v1/candidate/profile", json=first_profile()).status_code == 401
    _, headers = sign_in(client, register, role="employer", email="employer@example.com")
    assert client.get("/api/v1/candidate/profile").status_code == 403
    assert (
        client.patch("/api/v1/candidate/profile", json=first_profile(), headers=headers).status_code
        == 403
    )
    _, _ = sign_in(client, register)
    assert (
        client.patch("/api/v1/candidate/profile", json=first_profile()).json()["error"]["code"]
        == "CSRF_INVALID"
    )


def test_another_candidate_cannot_read_or_overwrite_profile(client, register):
    first, headers = sign_in(client, register)
    assert (
        client.patch("/api/v1/candidate/profile", json=first_profile(), headers=headers).status_code
        == 200
    )
    second, other_headers = sign_in(client, register, email="second@example.com")
    own = client.get("/api/v1/candidate/profile").json()
    assert own["candidate_id"] == second["id"] and own["full_name"] == ""
    assert client.get(f"/api/v1/candidate/profile/{first['id']}").status_code == 404
    assert (
        client.patch(
            "/api/v1/candidate/profile",
            json=first_profile(candidate_id=first["id"]),
            headers=other_headers,
        ).status_code
        == 422
    )
    client.post("/api/v1/auth/login", json={"email": "candidate@example.com", "password": PASSWORD})
    assert client.get("/api/v1/candidate/profile").json()["full_name"] == "Иван Петров"


def test_version_conflict_does_not_update_contacts_or_audit(app, client, register):
    _, headers = sign_in(client, register)
    client.patch("/api/v1/candidate/profile", json=first_profile(), headers=headers)
    assert (
        client.patch(
            "/api/v1/candidate/profile",
            json={"expected_version": 1, "full_name": "Новая версия"},
            headers=headers,
        ).status_code
        == 200
    )
    response = client.patch(
        "/api/v1/candidate/profile",
        json={"expected_version": 1, "contacts": {"email": "lost@example.com"}},
        headers=headers,
    )
    assert response.status_code == 409
    assert (
        client.get("/api/v1/candidate/profile").json()["contacts"]["email"] == "contact@example.com"
    )
    with app.state.session_factory() as db:
        assert (
            db.scalar(
                select(func.count())
                .select_from(AuditEvent)
                .where(AuditEvent.action == "profile.saved")
            )
            == 2
        )


def test_simultaneous_profile_update_has_one_winner(app, client, register):
    _, headers = sign_in(client, register)
    client.patch("/api/v1/candidate/profile", json=first_profile(), headers=headers)
    cookie = client.cookies.get("signal_session")

    def save(name):
        with TestClient(app) as other:
            other.cookies.set("signal_session", cookie)
            return other.patch(
                "/api/v1/candidate/profile",
                json={"expected_version": 1, "full_name": name},
                headers=headers,
            ).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(save, ["Версия А", "Версия Б"])) == [200, 409]
    assert client.get("/api/v1/candidate/profile").json()["version"] == 2


def test_assessment_port_is_injected_without_fake_publication(app, client, register):
    from app.contracts.schemas import VerifiedCategory
    from app.core.db import utcnow

    class FakeAssessmentRead:
        def get_verified(self, candidate_id):
            return VerifiedCategory(
                candidate_id=candidate_id,
                category_code="backend:middle",
                specialization="backend",
                verified_grade="middle",
                test_score=90,
                assessment_id=UUID("20000000-0000-4000-8000-000000000001"),
                assessment_version="test-v1",
                assigned_at=utcnow(),
                next_change_at=utcnow(),
                skills=[],
            )

    app.state.assessment_read_factory = lambda db: FakeAssessmentRead()
    sign_in(client, register)
    body = client.get("/api/v1/candidate/profile").json()
    assert body["verified_category"]["category_code"] == "backend:middle"
    assert not body["privacy"]["discoverable"]


def test_invitation_foundation_enforces_active_uniqueness(app, client, register):
    actor, headers = sign_in(client, register)
    client.patch("/api/v1/candidate/profile", json=first_profile(), headers=headers)

    def invitation(key):
        return Invitation(
            candidate_id=actor["id"],
            company_id="30000000-0000-4000-8000-000000000001",
            company_name="Тестовая компания",
            description="Разрабатывать API",
            company_contact="hr@example.com",
            salary_min=100000,
            salary_max=150000,
            idempotency_key=key,
            payload_hash="a" * 64,
        )

    with app.state.session_factory.begin() as db:
        db.add(invitation("first"))
    with pytest.raises(IntegrityError), app.state.session_factory.begin() as db:
        db.add(invitation("second"))
    with app.state.session_factory() as db:
        assert db.scalar(select(func.count()).select_from(ContactGrant)) == 0
        assert db.get(User, actor["id"]) is not None
