from uuid import UUID

import pytest
from sqlalchemy import func, select
from test_profiles import first_profile

from app.modules.profiles.models import ProfileConsent

COMPANY = "20000000-0000-4000-8000-000000000001"


def publish(client, headers, version=1, fields=None):
    payload = {
        "expected_version": version,
        "publication_enabled": True,
        "publication_consent_accepted": True,
        "publication_consent_version": "publication-v1",
    }
    if fields is not None:
        payload["visible_fields"] = fields
    return client.patch("/api/v1/candidate/privacy", json=payload, headers=headers)


def prepared(d_world, verified=True, assessment=True):
    client, candidate_id, headers = d_world["account"]("candidate@example.com", verified=verified)
    assert (
        client.patch("/api/v1/candidate/profile", json=first_profile(), headers=headers).status_code
        == 200
    )
    if assessment:
        d_world["assessments"].verify(candidate_id)
    return client, candidate_id, headers


def test_live_projection_hidden_fields_and_withdrawal(app, d_world):
    client, candidate_id, headers = prepared(d_world)
    employer, _, _ = d_world["account"]("employer@example.com", "employer", company_id=COMPANY)
    assert employer.get(f"/api/v1/employer/candidates/{candidate_id}").status_code == 404
    response = publish(client, headers, fields=["roles"])
    assert response.status_code == 200 and response.json()["discoverable"]
    public = employer.get(f"/api/v1/employer/candidates/{candidate_id}")
    assert public.status_code == 200
    body = public.json()
    assert (
        body["roles"] == ["backend"]
        and body["experience_months"] is None
        and body["declared_stack"] is None
    )
    assert body["hidden_fields"] == ["declared_stack", "experience_months"]
    assert body["display_name"].startswith("Кандидат ")
    for private in (
        "Иван Петров",
        "contact@example.com",
        "+7 900",
        "Создавал API",
        "resume_text",
        "contact_method",
    ):
        assert private not in public.text
    assert len(employer.get("/api/v1/employer/candidates").json()["items"]) == 1
    old_snapshot_id = body["candidate_id"]
    hidden = client.patch(
        "/api/v1/candidate/privacy",
        json={"expected_version": 2, "publication_enabled": False},
        headers=headers,
    )
    assert hidden.status_code == 200 and not hidden.json()["discoverable"]
    assert not hidden.json()["publication_consent_active"]
    assert employer.get(f"/api/v1/employer/candidates/{old_snapshot_id}").status_code == 404
    assert employer.get("/api/v1/employer/candidates").json()["items"] == []
    with app.state.session_factory() as db:
        port = app.state.profile_read_factory(db)
        assert not port.is_discoverable(UUID(candidate_id))
        assert (
            db.scalar(
                select(func.count())
                .select_from(ProfileConsent)
                .where(ProfileConsent.consent_type == "publication")
            )
            == 1
        )


def test_pending_category_and_no_fsp_are_distinct(d_world):
    client, candidate_id, headers = prepared(d_world, assessment=False)
    response = publish(client, headers)
    assert response.status_code == 200 and response.json()["publication_consent_active"]
    assert (
        not response.json()["discoverable"]
        and "category_not_verified" in response.json()["blocked_reasons"]
    )
    d_world["assessments"].verify(candidate_id)
    assert client.get("/api/v1/candidate/privacy").json()["discoverable"]
    assert client.get("/api/v1/candidate/profile").json()["fsp"]["status"] == "not_linked"
    del d_world["assessments"].categories[candidate_id]
    assert not client.get("/api/v1/candidate/privacy").json()["discoverable"]


def test_profile_processing_revocation_hides_and_requires_new_consent(d_world):
    client, _, headers = prepared(d_world)
    assert publish(client, headers).status_code == 200
    response = client.post(
        "/api/v1/candidate/consents",
        json={
            "expected_version": 2,
            "consent_type": "profile_processing",
            "action": "revoke",
            "version": "profile-processing-v1",
        },
        headers=headers,
    )
    assert response.status_code == 200 and not response.json()["publication_enabled"]
    assert not response.json()["processing_consent_active"]
    denied = client.patch(
        "/api/v1/candidate/profile",
        json={"expected_version": 3, "full_name": "Новое имя"},
        headers=headers,
    )
    assert denied.status_code == 422
    assert client.get("/api/v1/candidate/profile").json()["full_name"] == "Иван Петров"


@pytest.mark.parametrize("verified,complete,expected", [(False, True, 403), (True, False, 422)])
def test_publication_requires_verified_complete_profile(d_world, verified, complete, expected):
    client, _, headers = d_world["account"]("candidate@example.com", verified=verified)
    assert (
        client.patch(
            "/api/v1/candidate/profile",
            json=first_profile(**({} if complete else {"roles": []})),
            headers=headers,
        ).status_code
        == 200
    )
    assert publish(client, headers).status_code == expected
    assert client.get("/api/v1/candidate/privacy").json()["version"] == 1


@pytest.mark.parametrize(
    "change",
    [
        {"visible_fields": ["email"]},
        {"publication_enabled": True},
        {"candidate_id": COMPANY},
        {"visible_fields": None},
        {"publication_enabled": None},
        {"publication_enabled": 1},
    ],
)
def test_invalid_privacy_cannot_partially_write(d_world, change):
    client, _, headers = prepared(d_world)
    response = client.patch(
        "/api/v1/candidate/privacy", json={"expected_version": 1, **change}, headers=headers
    )
    assert response.status_code == 422
    assert client.get("/api/v1/candidate/privacy").json()["version"] == 1


def test_stale_privacy_and_contact_like_stack_tags(d_world):
    client, candidate_id, headers = prepared(d_world)
    client.patch(
        "/api/v1/candidate/profile",
        json={
            "expected_version": 1,
            "declared_stack": [
                "python",
                "private@example.com",
                "+7 900 000 00 00",
                "https://private.ru",
            ],
        },
        headers=headers,
    )
    assert publish(client, headers, version=1).status_code == 409
    assert publish(client, headers, version=2).status_code == 200
    employer, _, _ = d_world["account"]("employer@example.com", "employer", company_id=COMPANY)
    assert employer.get(f"/api/v1/employer/candidates/{candidate_id}").json()["declared_stack"] == [
        "python"
    ]
