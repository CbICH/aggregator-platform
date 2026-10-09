"""Live B/C/D/FSP matching and saved-result privacy, without fixture candidates."""

from uuid import UUID, uuid4

import pytest
from test_assessment import correct_answers
from test_bcd_integration import COMPANY, account
from test_profiles import first_profile

from app.contracts.schemas import ActorContext, FspEvidence
from app.modules.matching.models import SearchSnapshot
from app.modules.matching.schemas import SearchFilters
from app.modules.matching.service import MatchingService, score_profile

NEED = {
    "title": "Разработка API заказов",
    "description": "Разрабатывайте API нашей команды продукта.",
    "specialization": "backend",
    "grades": ["middle"],
    "declared_stack": ["python"],
    "required_skills": [{"id": "api.idempotency", "weight": 2}],
    "work_format": "remote",
    "salary_min": 120000,
    "salary_max": 160000,
}


@pytest.fixture
def matching_world(app):
    clients = []
    candidates = []
    for email in ("demo-fsp-winner@example.com", "demo-fsp-empty@example.com"):
        client, actor, headers = account(app, email, "candidate")
        clients.append(client)
        profile = {
            **first_profile(),
            "full_name": "Приватное Имя Кандидата",
            "declared_stack": ["Python", "PostgreSQL", "private-contact@example.com"],
        }
        assert (
            client.patch("/api/v1/candidate/profile", headers=headers, json=profile).status_code
            == 200
        )
        assert (
            client.post(
                "/api/v1/candidate/surveys",
                headers=headers,
                json={
                    "industry": "ИТ",
                    "specialization": "backend",
                    "declared_grade": "middle",
                    "roles": ["Backend"],
                    "experience_months": 24,
                },
            ).status_code
            == 201
        )
        attempt = client.post(
            "/api/v1/assessments",
            headers=headers,
            json={"specialization": "backend", "target_grade": "middle"},
        ).json()
        assert (
            client.put(
                f"/api/v1/assessments/{attempt['id']}/answers",
                headers=headers,
                json={"answers": correct_answers(app, attempt["id"])},
            ).status_code
            == 200
        )
        assert (
            client.post(f"/api/v1/assessments/{attempt['id']}/submit", headers=headers).json()[
                "score"
            ]
            == 100
        )
        assert (
            client.post(
                "/api/v1/candidate/category/confirm",
                headers=headers,
                json={"assessment_id": attempt["id"]},
            ).status_code
            == 200
        )
        published = client.patch(
            "/api/v1/candidate/privacy",
            headers=headers,
            json={
                "expected_version": 1,
                "publication_enabled": True,
                "publication_consent_accepted": True,
                "publication_consent_version": "publication-v1",
                "visible_fields": ["roles", "declared_stack", "experience_months"],
            },
        )
        assert published.status_code == 200
        own_id = client.get("/api/v1/candidate/fsp").json()["available_fsp_id"]
        assert (
            client.post(
                "/api/v1/candidate/fsp-link", headers=headers, json={"fsp_id": own_id}
            ).status_code
            == 200
        )
        candidates.append((client, actor, headers))
    employer, actor, headers = account(app, "matching-owner@example.com", "employer")
    clients.append(employer)
    company = employer.post("/api/v1/company", headers=headers, json=COMPANY)
    assert company.status_code == 201
    other, _, oh = account(app, "matching-other@example.com", "employer")
    clients.append(other)
    assert (
        other.post(
            "/api/v1/company", headers=oh, json={**COMPANY, "name": "Другая компания"}
        ).status_code
        == 201
    )
    need = employer.post("/api/v1/employer/needs", headers=headers, json=NEED)
    assert need.status_code == 201, need.text
    yield {
        "employer": employer,
        "actor": actor,
        "headers": headers,
        "other": other,
        "oh": oh,
        "company_id": company.json()["id"],
        "need_id": need.json()["id"],
        "candidates": candidates,
    }
    for client in clients:
        client.close()


def test_live_matching_uses_actual_category_fsp_and_all_filters(matching_world):
    world = matching_world
    client = world["employer"]
    winner = world["candidates"][0][1]["id"]
    empty = world["candidates"][1][1]["id"]
    result = client.get("/api/v1/employer/matching/candidates").json()
    assert [row["candidate_id"] for row in result["items"]] == [winner, empty]
    assert [row["score"] for row in result["items"]] == [100, 90]
    assert all(row["verified_category"]["test_score"] == 100 for row in result["items"])
    assert all("fsp_id" not in row for row in result["items"])
    serialized = client.get("/api/v1/employer/matching/candidates").text
    assert all(
        value not in serialized
        for value in (
            "Приватное Имя",
            "private-contact@example.com",
            "contact@example.com",
            "demo-winner-001",
        )
    )
    need = client.get(
        "/api/v1/employer/matching/candidates",
        params={
            "need_id": world["need_id"],
            "stack": " PYTHON ",
            "category_code": "backend:middle",
        },
    ).json()
    assert need["applied_need_id"] == world["need_id"] and need["total"] == 2
    assert need["items"][0]["components"] == {"test": 100, "relevance": 100, "fsp": 100}
    fsp = client.get("/api/v1/employer/matching/candidates?with_fsp_only=true").json()
    assert [row["candidate_id"] for row in fsp["items"]] == [winner]
    for params in (
        {"specialization": "qa"},
        {"grade": "junior"},
        {"category_code": "qa:senior"},
        {"stack": "no-such-technology"},
    ):
        assert (
            client.get("/api/v1/employer/matching/candidates", params=params).json()["total"] == 0
        )
    assert client.get("/api/v1/employer/matching/candidates?stack=%20").status_code == 422
    first = client.get("/api/v1/employer/matching/candidates?limit=1").json()
    second = client.get("/api/v1/employer/matching/candidates?limit=1&offset=1").json()
    assert first["next_offset"] == 1 and second["next_offset"] is None
    assert first["items"][0]["candidate_id"] != second["items"][0]["candidate_id"]
    categories = client.get("/api/v1/employer/categories").json()["items"]
    assert (
        next(row for row in categories if row["code"] == "backend:middle")["candidate_count"] == 2
    )


def test_search_history_rechecks_hidden_fields_and_revocation(app, matching_world):
    world = matching_world
    client = world["employer"]
    h = world["headers"]
    original = client.post("/api/v1/employer/searches", headers=h, json={})
    assert original.status_code == 201, original.text
    sid = original.json()["id"]
    refined = client.post(
        "/api/v1/employer/searches", headers=h, json={"with_fsp_only": True}
    ).json()
    assert refined["total"] == 1 and sid != refined["id"]
    history = client.get("/api/v1/employer/searches?limit=1").json()
    assert history["next_offset"] == 1
    assert client.get("/api/v1/employer/searches?limit=1&offset=1").json()["items"][0]["id"] == sid
    assert world["other"].get(f"/api/v1/employer/searches/{sid}").status_code == 404
    assert world["other"].get("/api/v1/employer/searches").json()["items"] == []
    candidate, actor, ch = world["candidates"][0]
    assert (
        candidate.patch(
            "/api/v1/candidate/privacy",
            headers=ch,
            json={"expected_version": 2, "visible_fields": []},
        ).status_code
        == 200
    )
    current = client.get(f"/api/v1/employer/searches/{sid}").json()
    hidden = next(row for row in current["items"] if row["candidate_id"] == actor["id"])
    assert (
        hidden["declared_stack"] is None
        and hidden["experience_years"] is None
        and hidden["roles"] is None
    )
    assert client.get("/api/v1/employer/matching/candidates?stack=python").json()["total"] == 1
    assert (
        candidate.patch(
            "/api/v1/candidate/privacy",
            headers=ch,
            json={"expected_version": 3, "publication_enabled": False},
        ).status_code
        == 200
    )
    reopened = client.get(f"/api/v1/employer/searches/{sid}").json()
    assert (
        reopened["original_total"] == 2
        and reopened["total"] == 1
        and reopened["unavailable_count"] == 1
    )
    assert actor["id"] not in [row["candidate_id"] for row in reopened["items"]]
    assert client.get(f"/api/v1/employer/searches/{refined['id']}").json()["items"] == []
    with app.state.session_factory() as db:
        stored = db.get(SearchSnapshot, sid)
        assert len(stored.candidate_ids) == 2
        assert set(stored.filters) == set(SearchFilters.model_fields)
        assert all("@" not in value for value in stored.candidate_ids)
    assert candidate.get("/api/v1/employer/searches").status_code == 403
    assert client.post("/api/v1/employer/searches", json={}).status_code == 403
    assert (
        world["other"]
        .post("/api/v1/employer/searches", headers=world["oh"], json={"need_id": world["need_id"]})
        .status_code
        == 404
    )


def test_fsp_unlink_and_outage_affect_live_and_saved_scores(app, matching_world):
    world = matching_world
    client = world["employer"]
    snapshot = client.post("/api/v1/employer/searches", headers=world["headers"], json={}).json()
    candidate, actor, ch = world["candidates"][0]
    app.state.fsp_registry.available = False
    unavailable = client.get("/api/v1/employer/matching/candidates").json()
    assert unavailable["total"] == 2 and all(
        row["fsp_status"] == "unavailable" for row in unavailable["items"]
    )
    assert all(row["score"] == 90 for row in unavailable["items"])
    assert (
        client.get("/api/v1/employer/matching/candidates?with_fsp_only=true").json()["total"] == 0
    )
    app.state.fsp_registry.available = True
    assert candidate.delete("/api/v1/candidate/fsp-link", headers=ch).status_code == 200
    saved = client.get(f"/api/v1/employer/searches/{snapshot['id']}").json()
    row = next(item for item in saved["items"] if item["candidate_id"] == actor["id"])
    assert (
        row["fsp_status"] == "not_linked" and row["score"] == 90 and row["fsp_achievements"] == []
    )
    assert (
        client.get("/api/v1/employer/matching/candidates?with_fsp_only=true").json()["total"] == 0
    )


def test_test_strength_dominates_fsp_bonus_and_declared_resume(app, matching_world):
    world = matching_world
    with app.state.session_factory() as db:
        actor = ActorContext(
            user_id=world["actor"]["id"],
            role="employer",
            email_verified=True,
            company_id=world["company_id"],
        )
        profile = app.state.profile_read_factory(db).get_public(
            UUID(world["candidates"][0][1]["id"]), actor
        )
        strong = profile.model_copy(deep=True)
        strong.verified_category.test_score = 95
        weak = profile.model_copy(deep=True)
        weak.verified_category.test_score = 60
        assert (
            score_profile(strong, FspEvidence(status="not_linked"), None).score
            > score_profile(weak, FspEvidence(status="linked_with_data", signal=100), None).score
        )
        altered = strong.model_copy(
            update={"declared_stack": ["go"], "experience_months": 999, "roles": ["other"]}
        )
        assert (
            score_profile(strong, FspEvidence(status="not_linked"), None).score
            == score_profile(altered, FspEvidence(status="not_linked"), None).score
        )
        service = MatchingService(
            db,
            app.state.profile_read_factory(db),
            app.state.assessment_read_factory(db),
            app.state.fsp_read_factory(db),
        )
        assert (
            service.search(actor, SearchFilters()).model_dump()
            == service.search(actor, SearchFilters()).model_dump()
        )


@pytest.mark.parametrize(
    "patch",
    [
        {"title": "    "},
        {"required_skills": [{"id": "unknown.skill", "weight": 1}]},
        {"required_skills": [{"id": "qa.test_design", "weight": 1}]},
        {
            "required_skills": [
                {"id": "api.idempotency", "weight": 1},
                {"id": "api.idempotency", "weight": 2},
            ]
        },
        {"salary_max": None},
        {"company_id": str(uuid4())},
    ],
)
def test_need_rejects_ambiguous_or_foreign_fields(app, patch):
    client, _, h = account(app, "need-validation@example.com", "employer")
    try:
        client.post("/api/v1/company", headers=h, json=COMPANY)
        assert (
            client.post("/api/v1/employer/needs", headers=h, json={**NEED, **patch}).status_code
            == 422
        )
    finally:
        client.close()
