from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from test_privacy import COMPANY, prepared, publish

from app.modules.invitations.models import ContactGrant, Invitation, InvitationEvent

OTHER_COMPANY = "20000000-0000-4000-8000-000000000002"


def setup_world(d_world):
    candidate, candidate_id, candidate_headers = prepared(d_world)
    assert publish(candidate, candidate_headers).status_code == 200
    employer, _, employer_headers = d_world["account"](
        "employer@example.com", "employer", company_id=COMPANY
    )
    return candidate, candidate_id, candidate_headers, employer, employer_headers


def offer(candidate_id, **changes):
    return {
        "candidate_id": candidate_id,
        "description": "Разрабатывайте Python API для системы заказов.",
        "salary": {"min": 100000, "max": 150000},
        "company_contact": "hr@example.com",
        "evidence_refs": ["python"],
        **changes,
    }


def send(employer, headers, candidate_id, key="test-offer-0001", **changes):
    return employer.post(
        "/api/v1/invitations",
        json=offer(candidate_id, **changes),
        headers={**headers, "Idempotency-Key": key},
    )


def decide(candidate, headers, invitation, action="accept", version=None):
    payload = {"expected_version": version or invitation["version"], "action": action}
    if action == "accept":
        payload.update(contact_consent_accepted=True, contact_consent_version="contact-transfer-v1")
    return candidate.post(
        f"/api/v1/invitations/{invitation['invitation_id']}/decision", json=payload, headers=headers
    )


def test_full_invitation_flow_and_snapshot(app, d_world):
    candidate, candidate_id, ch, employer, eh = setup_world(d_world)
    created = send(employer, eh, candidate_id)
    assert created.status_code == 201, created.text
    row = created.json()
    assert row["vacancy_id"] is None and row["salary"]["currency"] == "RUB"
    assert row["evidence"][0]["skill_id"] == "python" and row["evidence"][0]["score"] == 80
    assert not row["contact_access_active"]
    contact_url = f"/api/v1/employer/candidates/{candidate_id}/contacts"
    assert employer.get(contact_url).status_code == 404
    iid = row["invitation_id"]
    assert candidate.get(f"/api/v1/invitations/{iid}").json()["status"] == "sent"
    viewed = candidate.post(f"/api/v1/invitations/{iid}/view", headers=ch).json()
    assert viewed["status"] == "viewed" and viewed["version"] == 2
    assert candidate.post(f"/api/v1/invitations/{iid}/view", headers=ch).json()["version"] == 2
    assert decide(candidate, ch, row).status_code == 409
    accepted = decide(candidate, ch, viewed)
    assert accepted.status_code == 200 and accepted.json()["status"] == "accepted"
    assert accepted.json()["contact_access_active"]
    assert employer.get(contact_url).json()["email"] == "contact@example.com"
    assert employer.get("/api/v1/invitations").json()["items"][0]["status"] == "accepted"
    # Updating C/B or withdrawing publication cannot rewrite the sent conditions.
    d_world["companies"].companies[COMPANY].name = "Новое имя компании"
    d_world["assessments"].categories[candidate_id].skills[0].score = 10
    candidate.patch(
        "/api/v1/candidate/privacy",
        json={"expected_version": 2, "publication_enabled": False},
        headers=ch,
    )
    snapshot = employer.get(f"/api/v1/invitations/{iid}").json()
    assert (
        snapshot["company_name"] == row["company_name"] and snapshot["evidence"] == row["evidence"]
    )
    assert employer.get(contact_url).status_code == 200
    for private in ["contact@example.com", "+7 900", "Иван Петров", "resume_text"]:
        assert private not in employer.get("/api/v1/invitations").text
    assert len(candidate.get(f"/api/v1/invitations/{iid}/events").json()["items"]) == 3
    with app.state.session_factory() as db:
        assert db.scalar(select(func.count()).select_from(ContactGrant)) == 1


def test_replay_and_different_payload_same_key(d_world):
    candidate, candidate_id, ch, employer, eh = setup_world(d_world)
    original = send(employer, eh, candidate_id).json()
    assert send(employer, eh, candidate_id).json() == original
    assert (
        send(
            employer, eh, candidate_id, description="Другое предложение с новыми условиями."
        ).status_code
        == 409
    )
    assert send(employer, eh, candidate_id, key="other-active-offer").status_code == 409
    assert decide(candidate, ch, original, "decline").status_code == 200
    assert send(employer, eh, candidate_id, key="next-offer-0002").status_code == 201


def test_revoked_contact_grant_is_not_resurrected_by_accept_replay(app, d_world):
    candidate, candidate_id, ch, employer, eh = setup_world(d_world)
    row = send(employer, eh, candidate_id).json()
    assert decide(candidate, ch, row).status_code == 200
    revoked = candidate.patch(
        "/api/v1/candidate/privacy",
        json={"expected_version": 2, "revoke_contact_access": True},
        headers=ch,
    )
    assert revoked.status_code == 200
    assert employer.get(f"/api/v1/employer/candidates/{candidate_id}/contacts").status_code == 404
    replay = decide(candidate, ch, row)
    assert replay.status_code == 200 and not replay.json()["contact_access_active"]
    assert decide(candidate, ch, row, "decline").status_code == 409
    with app.state.session_factory() as db:
        assert db.scalar(select(func.count()).select_from(ContactGrant)) == 1
        assert len(db.scalars(select(InvitationEvent)).all()) == 2


def test_foreign_candidate_company_and_employer_decision_are_denied(d_world):
    candidate, candidate_id, ch, employer, eh = setup_world(d_world)
    foreign_candidate, _, fch = d_world["account"]("foreign@example.com")
    foreign_employer, _, feh = d_world["account"](
        "other-employer@example.com", "employer", company_id=OTHER_COMPANY
    )
    row = send(employer, eh, candidate_id).json()
    iid = row["invitation_id"]
    for client in (foreign_candidate, foreign_employer):
        assert client.get(f"/api/v1/invitations/{iid}").status_code == 404
        assert client.get(f"/api/v1/invitations/{iid}/events").status_code == 404
        assert client.get("/api/v1/invitations").json()["items"] == []
    assert foreign_candidate.post(f"/api/v1/invitations/{iid}/view", headers=fch).status_code == 404
    assert decide(foreign_candidate, fch, row).status_code == 404
    assert decide(employer, eh, row).status_code == 403
    assert decide(candidate, ch, row).status_code == 200
    assert (
        foreign_employer.get(f"/api/v1/employer/candidates/{candidate_id}/contacts").status_code
        == 404
    )
    assert candidate.get(f"/api/v1/employer/candidates/{candidate_id}/contacts").status_code == 403


@pytest.mark.parametrize(
    "salary",
    [
        {"min": 0, "max": 1},
        {"min": 2, "max": 1},
        {"min": 1.5, "max": 2},
        {"min": True, "max": 2},
        {"min": 1, "max": 2, "currency": "USD"},
    ],
)
def test_invalid_salary_rejected_before_storage(app, d_world, salary):
    _, candidate_id, _, employer, eh = setup_world(d_world)
    assert send(employer, eh, candidate_id, salary=salary).status_code == 422
    with app.state.session_factory() as db:
        assert db.scalar(select(func.count()).select_from(Invitation)) == 0


@pytest.mark.parametrize(
    "change,expected",
    [
        ({"candidate_id": "10000000-0000-4000-8000-000000000099"}, 404),
        ({"company_id": OTHER_COMPANY}, 422),
        ({"evidence_refs": ["made-up"]}, 422),
        ({"vacancy_id": OTHER_COMPANY}, 422),
        ({"need_id": OTHER_COMPANY}, 404),
        ({"description": " " * 25}, 422),
        ({"company_contact": " "}, 422),
    ],
)
def test_invalid_refs_and_fields(d_world, change, expected):
    _, candidate_id, _, employer, eh = setup_world(d_world)
    if "candidate_id" in change:
        candidate_id = change.pop("candidate_id")
    assert send(employer, eh, candidate_id, **change).status_code == expected


def test_owned_need_and_csrf(d_world):
    candidate, candidate_id, ch, employer, eh = setup_world(d_world)
    need_id = str(uuid4())
    d_world["companies"].needs[need_id] = COMPANY
    assert send(employer, {}, candidate_id, need_id=need_id).status_code == 403
    row = send(employer, eh, candidate_id, need_id=need_id).json()
    assert row["need_id"] == need_id
    assert (
        candidate.post(
            f"/api/v1/invitations/{row['invitation_id']}/decision",
            json={"action": "accept", "expected_version": 1},
            headers=ch,
        ).status_code
        == 422
    )
    assert decide(candidate, ch, row, "decline").status_code == 200
    assert decide(candidate, ch, row, "decline").status_code == 200
    assert employer.get(f"/api/v1/employer/candidates/{candidate_id}/contacts").status_code == 404


@pytest.mark.parametrize("actions", [("accept", "decline"), ("accept", "accept")])
def test_concurrent_decisions_have_one_final_status_and_one_event(app, d_world, actions):
    candidate, candidate_id, ch, employer, eh = setup_world(d_world)
    row = send(employer, eh, candidate_id).json()
    clients = [TestClient(app), TestClient(app)]
    for client in clients:
        client.cookies.update(candidate.cookies)
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(
            pool.map(
                lambda pair: decide(pair[0], ch, row, pair[1]), zip(clients, actions, strict=True)
            )
        )
    assert sorted(response.status_code for response in responses) == (
        [200, 200] if actions[0] == actions[1] else [200, 409]
    )
    final = candidate.get(f"/api/v1/invitations/{row['invitation_id']}").json()
    with app.state.session_factory() as db:
        assert db.scalar(select(func.count()).select_from(ContactGrant)) == (
            1 if final["status"] == "accepted" else 0
        )
        assert db.scalar(select(func.count()).select_from(InvitationEvent)) == 2
    for client in clients:
        client.close()


def test_concurrent_same_idempotency_key_has_single_invitation(app, d_world):
    _, candidate_id, _, employer, eh = setup_world(d_world)
    clients = [TestClient(app), TestClient(app)]
    for client in clients:
        client.cookies.update(employer.cookies)
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(lambda client: send(client, eh, candidate_id), clients))
    assert [response.status_code for response in responses] == [201, 201], [
        response.text for response in responses
    ]
    assert responses[0].json()["invitation_id"] == responses[1].json()["invitation_id"]
    with app.state.session_factory() as db:
        assert db.scalar(select(func.count()).select_from(Invitation)) == 1
        assert db.scalar(select(func.count()).select_from(InvitationEvent)) == 1
    for client in clients:
        client.close()
