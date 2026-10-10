"""Actual B/C/D composition, without replacing the persisted read adapters."""

from uuid import UUID, uuid4

from fastapi.testclient import TestClient
from test_assessment import correct_answers
from test_profiles import PASSWORD, first_profile

from app.modules.assessment.read import SqlAlchemyAssessmentRead
from app.modules.matching.read import SqlAlchemyCompanyRead


def account(app, email, role):
    client = TestClient(app)
    assert (
        client.post(
            "/api/v1/auth/register",
            json={
                "email": email,
                "password": PASSWORD,
                "role": role,
                "consent_accepted": True,
                "consent_version": "registration-v1",
            },
        ).status_code
        == 202
    )
    token = next(
        token for address, token in reversed(app.state.mailer.messages) if address == email
    )
    assert client.post("/api/v1/auth/verify-email", json={"token": token}).status_code == 200
    result = client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
    assert result.status_code == 200
    return client, result.json(), {"X-CSRF-Token": client.cookies.get("signal_csrf")}


COMPANY = {
    "name": "Интеграционная компания",
    "description": "Разрабатывает программные продукты.",
    "industry": "ИТ",
    "city": "Москва",
    "contact_name": "Тестовый руководитель",
    "contact_email": "hr@example.com",
}


def test_actual_b_category_c_company_d_invitation_contacts_and_revocation(app):
    candidate, actor, headers = account(app, "bcd-candidate@example.com", "candidate")
    employer, employer_actor, eh = account(app, "bcd-employer@example.com", "employer")
    other, _, oh = account(app, "bcd-other@example.com", "employer")
    try:
        company = employer.post("/api/v1/company", json=COMPANY, headers=eh)
        assert company.status_code == 201, company.text
        assert employer.get("/api/v1/me").json()["company_id"] == company.json()["id"]
        assert (
            other.post(
                "/api/v1/company", json={**COMPANY, "name": "Другая компания"}, headers=oh
            ).status_code
            == 201
        )
        assert (
            candidate.patch(
                "/api/v1/candidate/profile", json=first_profile(), headers=headers
            ).status_code
            == 200
        )
        published = candidate.patch(
            "/api/v1/candidate/privacy",
            headers=headers,
            json={
                "expected_version": 1,
                "publication_enabled": True,
                "publication_consent_accepted": True,
                "publication_consent_version": "publication-v1",
            },
        )
        assert published.status_code == 200 and not published.json()["discoverable"]
        assert employer.get("/api/v1/employer/candidates").json()["items"] == []
        assert (
            candidate.post(
                "/api/v1/candidate/surveys",
                headers=headers,
                json={
                    "industry": "ИТ",
                    "specialization": "backend",
                    "declared_grade": "middle",
                    "roles": ["Backend developer"],
                    "experience_months": 24,
                },
            ).status_code
            == 201
        )
        attempt = candidate.post(
            "/api/v1/assessments",
            headers=headers,
            json={"specialization": "backend", "target_grade": "middle"},
        ).json()
        assert (
            candidate.put(
                f"/api/v1/assessments/{attempt['id']}/answers",
                headers=headers,
                json={"answers": correct_answers(app, attempt["id"])},
            ).status_code
            == 200
        )
        result = candidate.post(f"/api/v1/assessments/{attempt['id']}/submit", headers=headers)
        assert result.status_code == 200 and result.json()["score"] == 100
        assert (
            candidate.post(
                "/api/v1/candidate/category/confirm",
                headers=headers,
                json={"assessment_id": attempt["id"]},
            ).status_code
            == 200
        )
        profile = employer.get(f"/api/v1/employer/candidates/{actor['id']}")
        assert profile.status_code == 200, profile.text
        assert profile.json()["verified_category"]["assessment_id"] == attempt["id"]
        assert "contact@example.com" not in profile.text
        with app.state.session_factory() as db:
            assert isinstance(app.state.assessment_read_factory(db), SqlAlchemyAssessmentRead)
            port = app.state.company_read_factory(db)
            assert isinstance(port, SqlAlchemyCompanyRead)
            assert not port.owns_need(UUID(company.json()["id"]), uuid4())
        context = employer.get("/api/v1/employer/invitation-context").json()
        assert context["company_contact"] == COMPANY["contact_email"]
        need = employer.post(
            "/api/v1/employer/needs",
            headers=eh,
            json={
                "title": "Разработка интеграций",
                "description": "Нужен разработчик API для команды продукта.",
                "specialization": "backend",
                "grades": ["middle"],
                "required_skills": [{"id": "api.idempotency", "weight": 2}],
                "work_format": "remote",
                "salary_min": 120000,
                "salary_max": 160000,
            },
        )
        assert need.status_code == 201, need.text
        need_id = need.json()["id"]
        assert other.get(f"/api/v1/employer/needs/{need_id}").status_code == 404
        with app.state.session_factory() as db:
            port = app.state.company_read_factory(db)
            assert port.owns_need(UUID(company.json()["id"]), UUID(need_id))
            assert not port.owns_need(
                UUID(other.get("/api/v1/company").json()["id"]), UUID(need_id)
            )
        payload = {
            "candidate_id": actor["id"],
            "need_id": need_id,
            "description": "Разрабатывайте API и интеграции нашей команды.",
            "salary": {"min": 120000, "max": 160000},
            "company_contact": context["company_contact"],
            "evidence_refs": ["api.idempotency"],
        }
        offer = employer.post(
            "/api/v1/invitations",
            headers={**eh, "Idempotency-Key": "real-bcd-invitation"},
            json=payload,
        )
        assert offer.status_code == 201, offer.text
        row = offer.json()
        assert (
            row["company_id"] == company.json()["id"] and row["category_code"] == "backend:middle"
        )
        assert row["need_id"] == need_id
        assert row["evidence"][0]["assessment_id"] == attempt["id"]
        contact_url = f"/api/v1/employer/candidates/{actor['id']}/contacts"
        assert employer.get(contact_url).status_code == 404
        assert (
            employer.patch(
                "/api/v1/company", headers=eh, json={"name": "Новое название компании"}
            ).status_code
            == 200
        )
        assert (
            candidate.get(f"/api/v1/invitations/{row['invitation_id']}").json()["company_name"]
            == COMPANY["name"]
        )
        accepted = candidate.post(
            f"/api/v1/invitations/{row['invitation_id']}/decision",
            headers=headers,
            json={
                "action": "accept",
                "expected_version": row["version"],
                "contact_consent_accepted": True,
                "contact_consent_version": "contact-transfer-v1",
            },
        )
        assert accepted.status_code == 200, accepted.text
        assert employer.get(contact_url).json()["email"] == "contact@example.com"
        assert other.get(contact_url).status_code == 404
        assert (
            candidate.patch(
                "/api/v1/candidate/privacy",
                headers=headers,
                json={"expected_version": 2, "revoke_contact_access": True},
            ).status_code
            == 200
        )
        assert employer.get(contact_url).status_code == 404
    finally:
        candidate.close()
        employer.close()
        other.close()


def test_company_validation_roles_csrf_and_ownership(app):
    candidate, _, ch = account(app, "company-candidate@example.com", "candidate")
    employer, _, eh = account(app, "company-owner@example.com", "employer")
    try:
        assert candidate.post("/api/v1/company", headers=ch, json=COMPANY).status_code == 403
        assert employer.post("/api/v1/company", json=COMPANY).status_code == 403
        assert employer.get("/api/v1/company").status_code == 404
        assert employer.post("/api/v1/company", headers=eh, json=COMPANY).status_code == 201
        assert employer.post("/api/v1/company", headers=eh, json=COMPANY).status_code == 409
        updated = employer.patch("/api/v1/company", headers=eh, json={"contact_role": "Тимлид"})
        assert updated.status_code == 200 and updated.json()["contact_role"] == "Тимлид"
        cleared = employer.patch("/api/v1/company", headers=eh, json={"contact_role": None})
        assert cleared.status_code == 200 and cleared.json()["contact_role"] is None
        for payload in [
            {"name": None},
            {"name": "   "},
            {"contact_email": None},
            {"owner_user_id": str(uuid4())},
        ]:
            assert employer.patch("/api/v1/company", headers=eh, json=payload).status_code == 422
        assert employer.get("/api/v1/company").json()["name"] == COMPANY["name"]
    finally:
        candidate.close()
        employer.close()
