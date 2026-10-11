"""Own-ID association, four FSP states, consent and isolation in the real app."""

from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from test_bcd_integration import account
from test_profiles import PASSWORD, first_profile

from app.core.models import AuditEvent
from app.modules.fsp.models import FspLink


@pytest.mark.parametrize(
    "email,expected_status,signal",
    [
        ("demo-fsp-winner@example.com", "linked_with_data", 100),
        ("demo-fsp-winner+test@example.com", "linked_with_data", 100),
        ("demo-fsp-empty@example.com", "linked_empty", 0),
        ("ordinary-fsp@example.com", "linked_empty", 0),
    ],
)
def test_owned_fsp_link_persists_in_profile_and_can_be_removed(app, email, expected_status, signal):
    client, actor, headers = account(app, email, "candidate")
    try:
        assert (
            client.patch(
                "/api/v1/candidate/profile", headers=headers, json=first_profile()
            ).status_code
            == 200
        )
        before = client.get("/api/v1/candidate/fsp").json()
        assert before["status"] == "not_linked" and before["signal"] == 0
        command = {"fsp_id": before["available_fsp_id"]}
        assert client.post("/api/v1/candidate/fsp-link", json=command).status_code == 403
        for _ in range(2):
            linked = client.post("/api/v1/candidate/fsp-link", headers=headers, json=command)
            assert linked.status_code == 200, linked.text
            assert linked.json()["status"] == expected_status and linked.json()["signal"] == signal
        profile = client.get("/api/v1/candidate/profile").json()["fsp"]
        assert profile["fsp_id"] == command["fsp_id"] and profile["source"] == "demo"
        if signal:
            assert profile["achievements"][0]["result"] == "победитель"
        with app.state.session_factory() as db:
            assert db.scalar(select(func.count()).select_from(FspLink)) == 1
            assert (
                db.scalar(
                    select(func.count())
                    .select_from(AuditEvent)
                    .where(AuditEvent.action == "fsp.linked")
                )
                == 1
            )
            assert app.state.fsp_read_factory(db).get_evidence(UUID(actor["id"])).signal == signal
        with TestClient(app) as reopened:
            assert (
                reopened.post(
                    "/api/v1/auth/login", json={"email": email, "password": PASSWORD}
                ).status_code
                == 200
            )
            assert reopened.get("/api/v1/candidate/fsp").json()["fsp_id"] == command["fsp_id"]
        for _ in range(2):
            assert (
                client.delete("/api/v1/candidate/fsp-link", headers=headers).json()["status"]
                == "not_linked"
            )
        assert client.get("/api/v1/candidate/profile").json()["fsp"]["signal"] == 0
    finally:
        client.close()


def test_fsp_does_not_accept_another_identity_or_client_achievements(app):
    owner, actor, headers = account(app, "demo-fsp-winner@example.com", "candidate")
    other, _, oh = account(app, "other-fsp@example.com", "candidate")
    employer, _, eh = account(app, "employer-fsp@example.com", "employer")
    try:
        own_id = owner.get("/api/v1/candidate/fsp").json()["available_fsp_id"]
        assert (
            owner.post(
                "/api/v1/candidate/fsp-link", headers=headers, json={"fsp_id": own_id}
            ).status_code
            == 409
        )
        for client, h in ((owner, headers), (other, oh)):
            assert (
                client.patch(
                    "/api/v1/candidate/profile", headers=h, json=first_profile()
                ).status_code
                == 200
            )
        assert (
            other.post(
                "/api/v1/candidate/fsp-link", headers=oh, json={"fsp_id": own_id}
            ).status_code
            == 422
        )
        assert (
            owner.post(
                "/api/v1/candidate/fsp-link",
                headers=headers,
                json={"fsp_id": own_id, "signal": 100},
            ).status_code
            == 422
        )
        assert employer.get("/api/v1/candidate/fsp").status_code == 403
        assert (
            employer.post(
                "/api/v1/candidate/fsp-link", headers=eh, json={"fsp_id": own_id}
            ).status_code
            == 403
        )
        assert other.get(f"/api/v1/candidate/fsp/{actor['id']}").status_code == 404
        assert (
            owner.post(
                "/api/v1/candidate/fsp-link", headers=headers, json={"fsp_id": own_id}
            ).status_code
            == 200
        )
        assert other.delete("/api/v1/candidate/fsp-link", headers=oh).status_code == 200
        assert owner.get("/api/v1/candidate/fsp").json()["status"] == "linked_with_data"
        assert (
            owner.post(
                "/api/v1/candidate/consents",
                headers=headers,
                json={
                    "expected_version": 1,
                    "consent_type": "profile_processing",
                    "action": "revoke",
                    "version": "profile-processing-v1",
                },
            ).status_code
            == 200
        )
        assert (
            owner.post(
                "/api/v1/candidate/fsp-link", headers=headers, json={"fsp_id": own_id}
            ).status_code
            == 409
        )
    finally:
        owner.close()
        other.close()
        employer.close()


def test_unavailable_fsp_preserves_link_and_unlink_still_works(app):
    client, _, headers = account(app, "demo-fsp-finalist@example.com", "candidate")
    try:
        client.patch("/api/v1/candidate/profile", headers=headers, json=first_profile())
        own_id = client.get("/api/v1/candidate/fsp").json()["available_fsp_id"]
        assert (
            client.post(
                "/api/v1/candidate/fsp-link", headers=headers, json={"fsp_id": own_id}
            ).status_code
            == 200
        )
        app.state.fsp_registry.available = False
        assert client.get("/api/v1/candidate/fsp").json()["status"] == "unavailable"
        assert client.get("/api/v1/candidate/profile").json()["fsp"]["status"] == "unavailable"
        assert (
            client.post(
                "/api/v1/candidate/fsp-link", headers=headers, json={"fsp_id": own_id}
            ).status_code
            == 503
        )
        assert client.delete("/api/v1/candidate/fsp-link", headers=headers).status_code == 200
        with app.state.session_factory() as db:
            assert db.scalar(select(func.count()).select_from(FspLink)) == 0
        app.state.fsp_registry.available = True
        assert client.get("/api/v1/candidate/fsp").json()["status"] == "not_linked"
    finally:
        client.close()


def test_fsp_needs_confirmed_email(app):
    with TestClient(app) as client:
        client.post(
            "/api/v1/auth/register",
            json={
                "email": "unverified-fsp@example.com",
                "password": PASSWORD,
                "role": "candidate",
                "consent_accepted": True,
                "consent_version": "registration-v1",
            },
        )
        client.post(
            "/api/v1/auth/login", json={"email": "unverified-fsp@example.com", "password": PASSWORD}
        )
        assert client.get("/api/v1/candidate/fsp").status_code == 403
        assert (
            client.post(
                "/api/v1/candidate/fsp-link",
                headers={"X-CSRF-Token": client.cookies.get("signal_csrf")},
                json={"fsp_id": "demo-winner-001"},
            ).status_code
            == 403
        )
