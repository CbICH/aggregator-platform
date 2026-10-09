from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from uuid import UUID, uuid4

import pytest
from doubles import AssessmentDouble, CompanyDouble
from fastapi.testclient import TestClient
from seed_d import fixture_id, seed
from sqlalchemy import func, select, update
from test_invitations import decide, send, setup_world
from test_privacy import COMPANY, prepared, publish

from app.contracts.schemas import ActorContext, Role
from app.core.models import AuditEvent, RateWindow, User
from app.modules.invitations.models import ContactGrant, Invitation, InvitationEvent
from app.modules.profiles.models import CandidateProfile, ProfileConsent, VisibilitySettings
from app.modules.profiles.privacy import aware


def test_seed_is_repeatable_and_reads_only_visible_fields(tmp_path):
    from app.core.config import Settings
    from app.core.db import Base
    from app.main import create_app

    app = create_app(
        Settings(
            _env_file=None, app_env="test", database_url=f"sqlite:///{tmp_path / 'seed_test.db'}"
        )
    )
    Base.metadata.create_all(app.state.engine)
    assessments, companies = AssessmentDouble(), CompanyDouble()
    app.state.assessment_read_factory = lambda db: assessments
    app.state.company_read_factory = lambda db: companies
    scenarios = seed(app, assessments, companies)
    fixed_time = datetime.fromisoformat(scenarios["fixed_time"])
    with app.state.session_factory() as db:
        counts = [
            db.scalar(select(func.count()).select_from(model))
            for model in [User, ProfileConsent, Invitation, InvitationEvent, ContactGrant]
        ]
    seed(app, assessments, companies)
    with app.state.session_factory() as db:
        assert [
            db.scalar(select(func.count()).select_from(model))
            for model in [User, ProfileConsent, Invitation, InvitationEvent, ContactGrant]
        ] == counts
        actor = ActorContext(
            user_id="40000000-0000-4000-8000-000000000001",
            role=Role.EMPLOYER,
            email_verified=True,
            company_id=COMPANY,
        )
        profiles = app.state.profile_read_factory(db).list_public(actor, limit=20)
        assert len(profiles) == 3
        assert profiles[1].roles == ["backend"] and profiles[1].declared_stack is None
        assert {row.status for row in db.scalars(select(Invitation)).all()} == {
            "sent",
            "viewed",
            "accepted",
            "declined",
        }
        assert db.scalar(select(func.count()).select_from(ContactGrant)) == 1
        assert all(aware(user.created_at) == fixed_time for user in db.scalars(select(User)))
        assert all(aware(row.created_at) == fixed_time for row in db.scalars(select(Invitation)))
        grant = db.scalar(select(ContactGrant))
        assert grant.id == fixture_id(f"{grant.invitation_id}:grant")
        assert aware(grant.created_at) == fixed_time + timedelta(minutes=5)
        profile = db.get(CandidateProfile, "10000000-0000-4000-8000-000000000001")
        visibility = db.get(VisibilitySettings, profile.candidate_id)
        profile.resume_text = "Сведения, изменённые владельцем после загрузки фикстур."
        profile.version = 8
        visibility.publication_enabled = False
        grant.revoked_at = fixed_time + timedelta(days=1)
        db.commit()
    seed(app, assessments, companies)
    with app.state.session_factory() as db:
        profile = db.get(CandidateProfile, "10000000-0000-4000-8000-000000000001")
        assert profile.version == 8 and profile.resume_text.startswith("Сведения, изменённые")
        assert not db.get(VisibilitySettings, profile.candidate_id).publication_enabled
        assert aware(db.scalar(select(ContactGrant)).revoked_at) == fixed_time + timedelta(days=1)
    app.state.engine.dispose()


def test_consent_versions_and_strict_acceptance(d_world):
    client, _, headers = prepared(d_world)
    invalid = publish(client, headers)
    assert invalid.status_code == 200
    response = client.patch(
        "/api/v1/candidate/privacy",
        json={
            "expected_version": 2,
            "publication_enabled": True,
            "publication_consent_accepted": 1,
            "publication_consent_version": "publication-v1",
        },
        headers=headers,
    )
    assert response.status_code == 422
    response = client.post(
        "/api/v1/candidate/consents",
        json={
            "expected_version": 2,
            "consent_type": "publication",
            "action": "revoke",
            "version": "old",
        },
        headers=headers,
    )
    assert response.status_code == 409
    response = client.post(
        "/api/v1/candidate/consents",
        json={
            "expected_version": 2,
            "consent_type": "publication",
            "action": "revoke",
            "version": "publication-v1",
        },
        headers=headers,
    )
    assert response.status_code == 200 and not response.json()["publication_enabled"]


def test_missing_production_ports_fail_closed(app, d_world):
    _, candidate_id, _, employer, eh = setup_world(d_world)
    del app.state.assessment_read_factory
    assert employer.get(f"/api/v1/employer/candidates/{candidate_id}").status_code == 404
    assert send(employer, eh, candidate_id).status_code == 404
    del app.state.company_read_factory
    assert employer.get("/api/v1/employer/candidates").status_code == 503


def test_public_ports_reject_wrong_actor_and_mismatched_category(app, d_world):
    client, candidate_id, headers = prepared(d_world)
    assert publish(client, headers).status_code == 200
    category = d_world["assessments"].categories[candidate_id]
    category.candidate_id = uuid4()
    with app.state.session_factory() as db:
        port = app.state.profile_read_factory(db)
        actor = ActorContext(user_id=candidate_id, role=Role.CANDIDATE, email_verified=True)
        assert port.get_public(UUID(candidate_id), actor) is None and port.list_public(actor) == []
        assert not port.is_discoverable(UUID(candidate_id))


def test_pagination_scope_and_input_bounds(d_world):
    candidate, candidate_id, ch, employer, eh = setup_world(d_world)
    for index in range(3):
        row = send(employer, eh, candidate_id, key=f"page-offer-{index}").json()
        assert decide(candidate, ch, row, "decline").status_code == 200
    first = employer.get("/api/v1/invitations?limit=1").json()
    second = employer.get(f"/api/v1/invitations?limit=1&cursor={first['next_cursor']}").json()
    assert first["items"][0]["invitation_id"] != second["items"][0]["invitation_id"]
    assert employer.get("/api/v1/invitations?limit=51").status_code == 422
    assert employer.get("/api/v1/invitations?cursor=not-uuid").status_code == 422
    assert (
        employer.post(
            "/api/v1/invitations", json={"candidate_id": candidate_id}, headers=eh
        ).status_code
        == 422
    )


def test_sending_rate_limit_and_existing_replay(app, d_world):
    candidate, candidate_id, ch, employer, eh = setup_world(d_world)
    original = send(employer, eh, candidate_id).json()
    with app.state.session_factory.begin() as db:
        db.execute(update(RateWindow).values(count=30))
    assert send(employer, eh, candidate_id).json()["invitation_id"] == original["invitation_id"]
    decide(candidate, ch, original, "decline")
    assert send(employer, eh, candidate_id, key="rate-limited-new").status_code == 429


@pytest.mark.parametrize("race", ["hide", "revoke"])
def test_decision_serializes_with_privacy_changes(app, d_world, race):
    candidate, candidate_id, ch, employer, eh = setup_world(d_world)
    row = send(employer, eh, candidate_id).json()
    decision_client, privacy_client = TestClient(app), TestClient(app)
    decision_client.cookies.update(candidate.cookies)
    privacy_client.cookies.update(candidate.cookies)

    def mutate():
        return privacy_client.patch(
            "/api/v1/candidate/privacy",
            json={
                "expected_version": 2,
                **(
                    {"publication_enabled": False}
                    if race == "hide"
                    else {"revoke_contact_access": True}
                ),
            },
            headers=ch,
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        future = pool.submit(decide, decision_client, ch, row)
        privacy = pool.submit(mutate).result()
        decision = future.result()
    assert privacy.status_code == decision.status_code == 200
    # Revoke ordered before a new explicit accept allows a new grant; revoke ordered after disables it.
    with app.state.session_factory() as db:
        assert db.scalar(select(func.count()).select_from(InvitationEvent)) == 2
        assert db.scalar(select(func.count()).select_from(ContactGrant)) == 1
        assert db.get(Invitation, row["invitation_id"]).status == "accepted"
    if race == "hide":
        assert not candidate.get("/api/v1/candidate/privacy").json()["publication_enabled"]
    decision_client.close()
    privacy_client.close()


def test_audit_and_validation_do_not_include_private_values(app, d_world, caplog):
    candidate, candidate_id, ch, employer, eh = setup_world(d_world)
    row = send(employer, eh, candidate_id).json()
    decide(candidate, ch, row)
    invalid = candidate.patch(
        "/api/v1/candidate/profile",
        json={"expected_version": 2, "contacts": {"phone": "SECRET_PRIVATE_PHONE"}},
        headers=ch,
    )
    assert invalid.status_code == 422 and "SECRET_PRIVATE_PHONE" not in invalid.text
    with app.state.session_factory() as db:
        events = db.scalars(select(AuditEvent)).all()
        serialized = str([(event.action, event.object_id, event.request_id) for event in events])
        assert "contact@example.com" not in serialized and "Создавал API" not in serialized
    assert "contact@example.com" not in caplog.text
