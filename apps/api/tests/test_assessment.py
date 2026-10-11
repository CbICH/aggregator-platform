import json
from datetime import timedelta
from uuid import UUID

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.contracts.ports import AssessmentRead
from app.core.db import utcnow
from app.core.errors import AppError
from app.modules.assessment.models import (
    AssessmentAttempt,
    AssessmentItem,
    GradeHistory,
    PilotEnrollment,
    PilotItem,
    PilotManualReview,
    PilotRun,
    Survey,
    VerifiedCategoryRecord,
)
from app.modules.assessment.pilot import (
    create_run,
    export_run,
    finalize_manual_review,
    parse_exclusion_reasons,
    record_manual_review,
    review_enrollment,
)
from app.modules.assessment.read import SqlAlchemyAssessmentRead
from app.modules.assessment.templates import (
    FAMILIES,
    TEMPLATES,
    build,
    passes_assessment,
    recommends_next_grade,
    score,
    templates_for,
)

PASSWORD = "correct horse battery"


def command(client, method, path, **kwargs):
    headers = {"X-CSRF-Token": client.cookies.get("signal_csrf", ""), **kwargs.pop("headers", {})}
    return client.request(method, path, headers=headers, **kwargs)


def login_verified(client, app, register, email="candidate@example.com"):
    register(email=email)
    token = app.state.mailer.messages[-1][1]
    assert client.post("/api/v1/auth/verify-email", json={"token": token}).status_code == 200
    assert (
        client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD}).status_code
        == 200
    )


def survey(client, *, specialization="backend", declared_grade="middle"):
    return command(
        client,
        "POST",
        "/api/v1/candidate/surveys",
        json={
            "industry": "Финтех",
            "specialization": specialization,
            "declared_grade": declared_grade,
            "roles": ["Backend developer"],
            "experience_months": 24,
        },
    )


def correct_answers(app, assessment_id):
    with app.state.session_factory() as db:
        items = db.scalars(
            select(AssessmentItem)
            .where(AssessmentItem.attempt_id == assessment_id)
            .order_by(AssessmentItem.position)
        ).all()
        return {
            item.id: {rule["field"]: rule["expected"] for rule in item.rubric} for item in items
        }


def answers_for_fields(app, assessment_id, fields_by_family):
    with app.state.session_factory() as db:
        items = db.scalars(
            select(AssessmentItem)
            .where(AssessmentItem.attempt_id == assessment_id)
            .order_by(AssessmentItem.position)
        ).all()
        return {
            item.id: {
                rule["field"]: rule["expected"]
                for rule in item.rubric
                if rule["field"] in fields_by_family[item.family]
            }
            for item in items
        }


def pilot_correct_answers(app, attempt_id):
    with app.state.session_factory() as db:
        items = db.scalars(
            select(PilotItem).where(PilotItem.attempt_id == attempt_id).order_by(PilotItem.position)
        ).all()
        return {
            item.id: {rule["field"]: rule["expected"] for rule in item.rubric} for item in items
        }


def create_pilot(app, *, specialization="backend", target_grade="middle"):
    with app.state.session_factory() as db:
        _, invite = create_run(db, specialization, target_grade, "assessment-v1")
        return invite


def finalize_pilot_manual_review(
    app,
    participant_code,
    reviewer_grades,
    *,
    resolved_grade=None,
    resolution_note="",
):
    with app.state.session_factory() as db:
        enrollment = db.scalar(
            select(PilotEnrollment).where(PilotEnrollment.participant_code == participant_code)
        )
        for index, grade in enumerate(reviewer_grades, start=1):
            record_manual_review(db, enrollment, f"reviewer-{index}", grade)
        return finalize_manual_review(
            db,
            enrollment,
            len(reviewer_grades),
            resolved_grade,
            resolution_note,
        )


def rubric_answers(rubric):
    return {rule["field"]: rule["expected"] for rule in rubric}


def typical_wrong_answers(prompt, rubric):
    questions = {question["name"]: question for question in prompt["questions"]}
    answers = {}
    for rule in rubric:
        question = questions[rule["field"]]
        if rule["kind"] == "set_equals":
            answers[rule["field"]] = [
                choice["id"]
                for choice in question["choices"]
                if choice["id"] not in rule["expected"]
            ][:1]
        elif isinstance(rule["expected"], int):
            answers[rule["field"]] = rule["expected"] + 1
        else:
            answers[rule["field"]] = next(
                choice["id"] for choice in question["choices"] if choice["id"] != rule["expected"]
            )
    return answers


def test_all_templates_generate_one_hundred_valid_variants_without_public_answers():
    assert len(TEMPLATES) == 18
    for template in TEMPLATES:
        prompts: set[str] = set()
        for variant in range(100):
            prompt, rubric = build(template, f"test-{template.id}-{variant}")
            assert (prompt, rubric) == build(template, f"test-{template.id}-{variant}")
            prompts.add(json.dumps(prompt, ensure_ascii=False, sort_keys=True))
            answers = rubric_answers(rubric)
            assert score(rubric, answers) == template.weight
            assert "expected" not in str(prompt)
            assert "seed" not in str(prompt).lower()
        assert len(prompts) == 100


def test_typical_wrong_answers_and_threshold_boundaries():
    for template in TEMPLATES:
        prompt, rubric = build(template, f"mistakes-{template.id}")
        assert score(rubric, typical_wrong_answers(prompt, rubric)) == 0
    critical = FAMILIES["backend"][:2]
    assert not passes_assessment(69, {"api": 40, "data": 35}, critical)
    assert passes_assessment(70, {"api": 20, "data": 17.5}, critical)
    assert not recommends_next_grade(84)
    assert recommends_next_grade(85)


def test_copied_answers_do_not_systematically_pass_different_variants():
    copied_passes = total_pairs = 0
    for specialization in FAMILIES:
        for grade in ("junior", "middle", "senior"):
            for pair in range(20):
                family_scores = {}
                for template in templates_for(specialization, grade):
                    _, source_rubric = build(template, f"copy-source-{template.id}-{pair}")
                    _, target_rubric = build(template, f"copy-target-{template.id}-{pair}")
                    family_scores[template.family] = score(
                        target_rubric, rubric_answers(source_rubric)
                    )
                total = sum(family_scores.values())
                copied_passes += passes_assessment(
                    total, family_scores, FAMILIES[specialization][:2]
                )
                total_pairs += 1
    assert total_pairs == 120
    assert copied_passes == 0


def test_assessment_full_flow_is_server_scored_and_category_is_explicit(app, client, register):
    login_verified(client, app, register)
    assert survey(client).status_code == 201
    started = command(
        client,
        "POST",
        "/api/v1/assessments",
        json={"specialization": "backend", "target_grade": "middle"},
    )
    assert started.status_code == 201
    assessment = started.json()
    assert len(assessment["items"]) == 3
    assert "private_seed" not in started.text and "rubric" not in started.text
    survey_history = client.get("/api/v1/candidate/surveys")
    assert survey_history.status_code == 200
    assert len(survey_history.json()["items"]) == 1
    assert survey_history.json()["items"][0]["industry"] == "Финтех"
    with app.state.session_factory.begin() as db:
        stored_attempt = db.get(AssessmentAttempt, assessment["id"])
        assert stored_attempt.survey_snapshot["industry"] == "Финтех"
        original_survey = db.get(Survey, stored_attempt.survey_id)
        original_survey.industry = "Ритейл"
    with app.state.session_factory() as db:
        assert db.get(AssessmentAttempt, assessment["id"]).survey_snapshot["industry"] == "Финтех"

    answer_payload = {"answers": correct_answers(app, assessment["id"])}
    assert (
        command(
            client, "PUT", f"/api/v1/assessments/{assessment['id']}/answers", json=answer_payload
        ).status_code
        == 200
    )
    reloaded = client.get(f"/api/v1/assessments/{assessment['id']}")
    assert reloaded.json()["deadline_at"] == assessment["deadline_at"]
    assert {item["id"]: item["answers"] for item in reloaded.json()["items"]} == answer_payload[
        "answers"
    ]
    result = command(client, "POST", f"/api/v1/assessments/{assessment['id']}/submit")
    assert result.status_code == 200 and result.json()["status"] == "passed"
    assert result.json()["score"] == 100
    assert (
        command(client, "POST", f"/api/v1/assessments/{assessment['id']}/submit").json()
        == result.json()
    )

    before = client.get("/api/v1/candidate/category").json()
    assert before["verified"] is None and before["provisional"]["id"] == assessment["id"]
    confirmed = command(
        client,
        "POST",
        "/api/v1/candidate/category/confirm",
        json={"assessment_id": assessment["id"]},
    )
    assert confirmed.status_code == 200
    assert confirmed.json()["verified"]["category_code"] == "backend:middle"
    category_history = client.get("/api/v1/candidate/category/history")
    assert category_history.status_code == 200
    assert category_history.json()["items"][0]["assessment_id"] == assessment["id"]
    assert category_history.json()["items"][0]["category_code"] == "backend:middle"
    assert (
        command(
            client,
            "POST",
            "/api/v1/candidate/category/confirm",
            json={"assessment_id": assessment["id"]},
        ).status_code
        == 200
    )
    with app.state.session_factory() as db:
        assert db.scalar(select(GradeHistory).where(GradeHistory.assessment_id == assessment["id"]))
        assert (
            len(
                db.scalars(
                    select(GradeHistory).where(GradeHistory.assessment_id == assessment["id"])
                ).all()
            )
            == 1
        )
    reader: AssessmentRead = app.state.assessment_read
    assert isinstance(reader, SqlAlchemyAssessmentRead)
    verified = reader.get_verified(UUID(confirmed.json()["verified"]["candidate_id"]))
    assert verified and verified.category_code == "backend:middle"
    assert verified.assessment_id == UUID(assessment["id"])
    cooldown = command(
        client,
        "POST",
        "/api/v1/assessments",
        json={"specialization": "backend", "target_grade": "senior"},
    )
    assert cooldown.status_code == 409
    assert cooldown.json()["error"]["code"] == "GRADE_CHANGE_COOLDOWN"
    cross_specialization = command(
        client,
        "POST",
        "/api/v1/assessments",
        json={"specialization": "qa", "target_grade": "junior"},
    )
    assert cross_specialization.status_code == 409
    assert cross_specialization.json()["error"]["code"] == "GRADE_CHANGE_COOLDOWN"
    with app.state.session_factory.begin() as db:
        db.get(
            VerifiedCategoryRecord, confirmed.json()["verified"]["candidate_id"]
        ).next_change_at = utcnow()
    lower = command(
        client,
        "POST",
        "/api/v1/assessments",
        json={"specialization": "backend", "target_grade": "junior"},
    )
    assert lower.status_code == 409
    assert lower.json()["error"]["code"] == "GRADE_NOT_ADVANCED"
    upgrade = command(
        client,
        "POST",
        "/api/v1/assessments",
        json={"specialization": "backend", "target_grade": "senior"},
    )
    assert upgrade.status_code == 201
    assert (
        command(client, "POST", f"/api/v1/assessments/{upgrade.json()['id']}/submit").json()[
            "status"
        ]
        == "failed"
    )
    assert (
        client.get("/api/v1/candidate/category").json()["verified"]["category_code"]
        == "backend:middle"
    )


def test_assessment_is_not_visible_or_submittable_by_another_candidate(app, client, register):
    login_verified(client, app, register)
    survey(client)
    assessment_id = command(
        client,
        "POST",
        "/api/v1/assessments",
        json={"specialization": "backend", "target_grade": "junior"},
    ).json()["id"]
    csrf = client.cookies.get("signal_csrf")
    client.post("/api/v1/auth/logout", headers={"X-CSRF-Token": csrf})
    login_verified(client, app, register, email="other@example.com")
    assert client.get(f"/api/v1/assessments/{assessment_id}").status_code == 404
    assert command(client, "POST", f"/api/v1/assessments/{assessment_id}/submit").status_code == 404


def test_survey_and_answer_payload_cannot_be_bypassed_or_tampered(app, client, register):
    login_verified(client, app, register)
    missing_survey = command(
        client,
        "POST",
        "/api/v1/assessments",
        json={"specialization": "backend", "target_grade": "middle"},
    )
    assert missing_survey.status_code == 409
    assert missing_survey.json()["error"]["code"] == "SURVEY_REQUIRED"
    invalid_survey = command(
        client,
        "POST",
        "/api/v1/candidate/surveys",
        json={
            "industry": "Финтех",
            "specialization": "backend",
            "declared_grade": "senior",
            "roles": [],
            "experience_months": 24,
        },
    )
    assert invalid_survey.status_code == 422
    survey(client, declared_grade="senior")
    attempt = command(
        client,
        "POST",
        "/api/v1/assessments",
        json={"specialization": "backend", "target_grade": "middle"},
    ).json()
    tampered = command(
        client,
        "PUT",
        f"/api/v1/assessments/{attempt['id']}/answers",
        json={"answers": {}, "verified_grade": "senior"},
    )
    assert tampered.status_code == 422
    assert client.get(f"/api/v1/assessments/{attempt['id']}").json()["target_grade"] == "middle"


def test_exact_threshold_and_critical_family_threshold_are_enforced(app, client, register):
    login_verified(client, app, register)
    survey(client)
    passed_attempt = command(
        client,
        "POST",
        "/api/v1/assessments",
        json={"specialization": "backend", "target_grade": "junior"},
    ).json()
    exact_threshold = answers_for_fields(
        app,
        passed_attempt["id"],
        {
            "api": {"created_orders"},
            "data": {"rows", "boundary"},
            "decision": {"pattern", "proof"},
        },
    )
    command(
        client,
        "PUT",
        f"/api/v1/assessments/{passed_attempt['id']}/answers",
        json={"answers": exact_threshold},
    )
    result = command(client, "POST", f"/api/v1/assessments/{passed_attempt['id']}/submit")
    assert result.status_code == 200
    assert result.json()["score"] == 70
    assert result.json()["passed"] is True

    csrf = client.cookies.get("signal_csrf")
    client.post("/api/v1/auth/logout", headers={"X-CSRF-Token": csrf})
    login_verified(client, app, register, email="critical-family@example.com")
    survey(client)
    failed_attempt = command(
        client,
        "POST",
        "/api/v1/assessments",
        json={"specialization": "backend", "target_grade": "junior"},
    ).json()
    critical_failure = answers_for_fields(
        app,
        failed_attempt["id"],
        {
            "api": {"retry"},
            "data": {"rows", "boundary", "duplicates"},
            "decision": {"pattern", "proof"},
        },
    )
    command(
        client,
        "PUT",
        f"/api/v1/assessments/{failed_attempt['id']}/answers",
        json={"answers": critical_failure},
    )
    result = command(client, "POST", f"/api/v1/assessments/{failed_attempt['id']}/submit")
    assert result.status_code == 200
    assert result.json()["score"] == 70
    assert result.json()["passed"] is False


def test_expired_assessment_cannot_be_edited_or_submitted(app, client, register):
    login_verified(client, app, register)
    survey(client)
    assessment = command(
        client,
        "POST",
        "/api/v1/assessments",
        json={"specialization": "backend", "target_grade": "junior"},
    ).json()
    with app.state.session_factory.begin() as db:
        db.get(AssessmentAttempt, assessment["id"]).deadline_at = utcnow() - timedelta(seconds=1)
    reloaded = client.get(f"/api/v1/assessments/{assessment['id']}")
    assert reloaded.status_code == 200 and reloaded.json()["status"] == "expired"
    update = command(
        client,
        "PUT",
        f"/api/v1/assessments/{assessment['id']}/answers",
        json={"answers": {}},
    )
    assert update.status_code == 409
    assert update.json()["error"]["code"] == "ASSESSMENT_EXPIRED"
    assert (
        command(client, "POST", f"/api/v1/assessments/{assessment['id']}/submit").status_code == 409
    )


def test_passed_result_expires_before_category_confirmation(app, client, register):
    login_verified(client, app, register)
    survey(client)
    attempt = command(
        client,
        "POST",
        "/api/v1/assessments",
        json={"specialization": "backend", "target_grade": "junior"},
    ).json()
    command(
        client,
        "PUT",
        f"/api/v1/assessments/{attempt['id']}/answers",
        json={"answers": correct_answers(app, attempt["id"])},
    )
    assert (
        command(client, "POST", f"/api/v1/assessments/{attempt['id']}/submit").json()["status"]
        == "passed"
    )
    with app.state.session_factory.begin() as db:
        db.get(AssessmentAttempt, attempt["id"]).submitted_at = utcnow() - timedelta(
            days=7, seconds=1
        )
    expired = command(
        client,
        "POST",
        "/api/v1/candidate/category/confirm",
        json={"assessment_id": attempt["id"]},
    )
    assert expired.status_code == 409
    assert expired.json()["error"]["code"] == "ASSESSMENT_RESULT_EXPIRED"


def test_catalog_exposes_exactly_the_six_server_scored_categories(client):
    catalog = client.get("/api/v1/catalogs")
    assert catalog.status_code == 200
    categories = catalog.json()["categories"]
    assert {item["id"] for item in categories} == {
        "backend:junior",
        "backend:middle",
        "backend:senior",
        "qa:junior",
        "qa:middle",
        "qa:senior",
    }
    assert all(item["active"] for item in categories)


def test_start_limits_and_failed_retry_delay_are_enforced(app, client, register):
    login_verified(client, app, register)
    survey(client)
    for grade in ("junior", "middle", "senior"):
        response = command(
            client,
            "POST",
            "/api/v1/assessments",
            json={"specialization": "backend", "target_grade": grade},
        )
        assert response.status_code == 201
    survey(client, specialization="qa")
    daily_limit = command(
        client,
        "POST",
        "/api/v1/assessments",
        json={"specialization": "qa", "target_grade": "junior"},
    )
    assert daily_limit.status_code == 429
    assert daily_limit.json()["error"]["code"] == "ASSESSMENT_DAILY_LIMIT"

    csrf = client.cookies.get("signal_csrf")
    client.post("/api/v1/auth/logout", headers={"X-CSRF-Token": csrf})
    login_verified(client, app, register, email="retry-delay@example.com")
    survey(client)
    failed = command(
        client,
        "POST",
        "/api/v1/assessments",
        json={"specialization": "backend", "target_grade": "junior"},
    ).json()
    assert (
        command(client, "POST", f"/api/v1/assessments/{failed['id']}/submit").json()["status"]
        == "failed"
    )
    retry = command(
        client,
        "POST",
        "/api/v1/assessments",
        json={"specialization": "backend", "target_grade": "junior"},
    )
    assert retry.status_code == 409
    assert retry.json()["error"]["code"] == "ASSESSMENT_RETRY_COOLDOWN"
    with app.state.session_factory.begin() as db:
        db.get(AssessmentAttempt, failed["id"]).submitted_at = utcnow() - timedelta(
            hours=24, seconds=1
        )
    assert (
        command(
            client,
            "POST",
            "/api/v1/assessments",
            json={"specialization": "backend", "target_grade": "junior"},
        ).status_code
        == 201
    )


def test_database_allows_only_one_active_attempt_for_the_same_target(app, client, register):
    login_verified(client, app, register)
    survey(client)
    started = command(
        client,
        "POST",
        "/api/v1/assessments",
        json={"specialization": "backend", "target_grade": "junior"},
    ).json()
    with app.state.session_factory() as db:
        original = db.get(AssessmentAttempt, started["id"])
        duplicate = AssessmentAttempt(
            candidate_id=original.candidate_id,
            survey_id=original.survey_id,
            survey_snapshot=original.survey_snapshot,
            specialization=original.specialization,
            target_grade=original.target_grade,
            catalog_version=original.catalog_version,
            deadline_at=original.deadline_at,
        )
        db.add(duplicate)
        with pytest.raises(IntegrityError):
            db.commit()


def test_failed_senior_attempt_never_creates_a_lower_category(app, client, register):
    login_verified(client, app, register)
    survey(client, declared_grade="senior")
    senior = command(
        client,
        "POST",
        "/api/v1/assessments",
        json={"specialization": "backend", "target_grade": "senior"},
    ).json()
    assert (
        command(client, "POST", f"/api/v1/assessments/{senior['id']}/submit").json()["status"]
        == "failed"
    )
    category = client.get("/api/v1/candidate/category").json()
    assert category["verified"] is None and category["provisional"] is None


def test_initial_candidate_can_choose_lower_and_keep_a_prior_provisional_pass(
    app, client, register
):
    login_verified(client, app, register)
    survey(client, declared_grade="senior")
    senior = command(
        client,
        "POST",
        "/api/v1/assessments",
        json={"specialization": "backend", "target_grade": "senior"},
    ).json()
    assert (
        command(client, "POST", f"/api/v1/assessments/{senior['id']}/submit").json()["status"]
        == "failed"
    )
    lower = command(
        client,
        "POST",
        "/api/v1/assessments",
        json={"specialization": "backend", "target_grade": "junior"},
    ).json()
    command(
        client,
        "PUT",
        f"/api/v1/assessments/{lower['id']}/answers",
        json={"answers": correct_answers(app, lower["id"])},
    )
    passed_lower = command(client, "POST", f"/api/v1/assessments/{lower['id']}/submit").json()
    assert passed_lower["status"] == "passed" and passed_lower["next_grade_recommended"] is True
    higher = command(
        client,
        "POST",
        "/api/v1/assessments",
        json={"specialization": "backend", "target_grade": "middle"},
    ).json()
    assert (
        command(client, "POST", f"/api/v1/assessments/{higher['id']}/submit").json()["status"]
        == "failed"
    )
    category = client.get("/api/v1/candidate/category").json()
    assert category["verified"] is None
    assert category["provisional"]["id"] == lower["id"]


def test_controlled_pilot_keeps_scores_and_answers_private_until_operator_review(
    app, client, register, tmp_path
):
    login_verified(client, app, register)
    invite = create_pilot(app)
    joined = command(client, "POST", "/api/v1/candidate/pilot/join", json={"invite_code": invite})
    assert joined.status_code == 201
    state = joined.json()
    participant_code = state["participant_code"]
    assert state["enrolled"] and participant_code.startswith("P-")
    assert invite not in joined.text and "manual_grade" not in joined.text
    waiting = command(client, "POST", "/api/v1/candidate/pilot/attempts")
    assert waiting.status_code == 409
    assert waiting.json()["error"]["code"] == "PILOT_MANUAL_REVIEW_REQUIRED"
    finalize_pilot_manual_review(app, participant_code, ["middle", "middle"])

    first = command(client, "POST", "/api/v1/candidate/pilot/attempts")
    assert first.status_code == 201
    first_attempt = first.json()
    assert first_attempt["form_code"] == "A"
    assert (
        "rubric" not in first.text
        and "score" not in first.text
        and len(first_attempt["items"]) == 3
    )
    first_answers = pilot_correct_answers(app, first_attempt["id"])
    assert (
        command(
            client,
            "PUT",
            f"/api/v1/candidate/pilot/attempts/{first_attempt['id']}/answers",
            json={"answers": first_answers},
        ).status_code
        == 200
    )
    first_submitted = command(
        client, "POST", f"/api/v1/candidate/pilot/attempts/{first_attempt['id']}/submit"
    )
    assert first_submitted.status_code == 200
    assert first_submitted.json()["status"] == "awaiting_manual_review"
    assert first_submitted.json()["items"] == [] and "score" not in first_submitted.text

    second = command(client, "POST", "/api/v1/candidate/pilot/attempts")
    assert second.status_code == 201
    second_attempt = second.json()
    assert second_attempt["form_code"] == "B"
    assert second_attempt["items"] != first_attempt["items"]
    second_answers = pilot_correct_answers(app, second_attempt["id"])
    command(
        client,
        "PUT",
        f"/api/v1/candidate/pilot/attempts/{second_attempt['id']}/answers",
        json={"answers": second_answers},
    )
    assert (
        command(
            client, "POST", f"/api/v1/candidate/pilot/attempts/{second_attempt['id']}/submit"
        ).json()["status"]
        == "awaiting_manual_review"
    )
    finished = client.get("/api/v1/candidate/pilot")
    assert finished.status_code == 200
    assert finished.json()["current_attempt"] is None
    assert {item["status"] for item in finished.json()["attempts"]} == {"awaiting_manual_review"}
    assert client.get("/api/v1/candidate/category").json()["verified"] is None
    assert client.get("/api/v1/candidate/assessments").json()["items"] == []

    with app.state.session_factory() as db:
        enrollment = db.scalar(
            select(PilotEnrollment).where(PilotEnrollment.participant_code == participant_code)
        )
        reviewed = review_enrollment(db, enrollment)
        assert {attempt.status for attempt in reviewed} == {"reviewed"}
    with app.state.session_factory() as db:
        enrollment = db.scalar(
            select(PilotEnrollment).where(PilotEnrollment.participant_code == participant_code)
        )
        run = db.get(PilotRun, enrollment.run_id)
        exported = export_run(
            db,
            run,
            tmp_path / "raw_results.csv",
            tmp_path / "metadata.json",
            {},
            method="Two independent team reviewers.",
        )
    assert exported == 1
    raw = (tmp_path / "raw_results.csv").read_text(encoding="utf-8")
    metadata = json.loads((tmp_path / "metadata.json").read_text(encoding="utf-8"))
    assert participant_code in raw and "candidate@example.com" not in raw
    assert metadata["manual_review"]["completed_before_automatic_scores"] is True
    assert metadata["exclusion_reasons"] == {}


def test_controlled_pilot_enrollment_stops_at_the_planned_capacity(app, client, register):
    login_verified(client, app, register)
    invite = create_pilot(app)
    with app.state.session_factory.begin() as db:
        run = db.scalar(select(PilotRun))
        run.max_participants = 1
    assert (
        command(
            client, "POST", "/api/v1/candidate/pilot/join", json={"invite_code": invite}
        ).status_code
        == 201
    )

    csrf = client.cookies.get("signal_csrf")
    client.post("/api/v1/auth/logout", headers={"X-CSRF-Token": csrf})
    login_verified(client, app, register, email="capacity-pilot@example.com")
    full = command(client, "POST", "/api/v1/candidate/pilot/join", json={"invite_code": invite})
    assert full.status_code == 409
    assert full.json()["error"]["code"] == "PILOT_CAPACITY_REACHED"


def test_independent_manual_reviews_must_be_recorded_and_resolved_before_forms(
    app, client, register
):
    login_verified(client, app, register)
    invite = create_pilot(app)
    participant_code = command(
        client, "POST", "/api/v1/candidate/pilot/join", json={"invite_code": invite}
    ).json()["participant_code"]
    with app.state.session_factory() as db:
        enrollment = db.scalar(
            select(PilotEnrollment).where(PilotEnrollment.participant_code == participant_code)
        )
        record_manual_review(db, enrollment, "reviewer-one", "middle")
        with pytest.raises(AppError) as incomplete:
            finalize_manual_review(db, enrollment, 2)
        assert incomplete.value.code == "PILOT_MANUAL_REVIEW_COUNT"
        record_manual_review(db, enrollment, "reviewer-two", "junior")
        with pytest.raises(AppError) as disagreement:
            finalize_manual_review(db, enrollment, 2)
        assert disagreement.value.code == "PILOT_MANUAL_REVIEW_DISAGREEMENT"
        finalized = finalize_manual_review(
            db,
            enrollment,
            2,
            "middle",
            "Рецензенты согласовали уровень по общей ручной рубрике.",
        )
        assert finalized.manual_grade == "middle"
        assert finalized.manual_reviewer_count == 2
        assert finalized.manual_review_resolution
        assert (
            db.scalar(
                select(PilotManualReview).where(PilotManualReview.enrollment_id == finalized.id)
            )
            is not None
        )
    assert command(client, "POST", "/api/v1/candidate/pilot/attempts").status_code == 201


def test_pilot_attempt_is_owned_and_must_be_fully_answered(app, client, register):
    login_verified(client, app, register)
    invite = create_pilot(app)
    joined = command(
        client, "POST", "/api/v1/candidate/pilot/join", json={"invite_code": invite}
    ).json()
    finalize_pilot_manual_review(app, joined["participant_code"], ["junior"])
    attempt = command(client, "POST", "/api/v1/candidate/pilot/attempts").json()
    incomplete = command(client, "POST", f"/api/v1/candidate/pilot/attempts/{attempt['id']}/submit")
    assert incomplete.status_code == 422
    assert incomplete.json()["error"]["code"] == "PILOT_ANSWERS_INCOMPLETE"

    csrf = client.cookies.get("signal_csrf")
    client.post("/api/v1/auth/logout", headers={"X-CSRF-Token": csrf})
    login_verified(client, app, register, email="another-pilot@example.com")
    assert client.get(f"/api/v1/candidate/pilot/attempts/{attempt['id']}").status_code == 404


def test_pilot_export_requires_explicit_reason_for_every_incomplete_observation(
    app, client, register, tmp_path
):
    login_verified(client, app, register)
    invite = create_pilot(app)
    joined = command(client, "POST", "/api/v1/candidate/pilot/join", json={"invite_code": invite})
    participant_code = joined.json()["participant_code"]
    with app.state.session_factory() as db:
        enrollment = db.scalar(
            select(PilotEnrollment).where(PilotEnrollment.participant_code == participant_code)
        )
        run = db.get(PilotRun, enrollment.run_id)
        with pytest.raises(AppError) as incomplete:
            export_run(
                db,
                run,
                tmp_path / "raw.csv",
                tmp_path / "metadata.json",
                {},
                method="Two reviewers.",
            )
        assert incomplete.value.code == "PILOT_EXPORT_INCOMPLETE"
        assert (
            export_run(
                db,
                run,
                tmp_path / "raw.csv",
                tmp_path / "metadata.json",
                {participant_code: "Did not complete both forms."},
                method="Two reviewers.",
            )
            == 0
        )
    metadata = json.loads((tmp_path / "metadata.json").read_text(encoding="utf-8"))
    assert metadata["exclusion_reasons"] == {participant_code: "Did not complete both forms."}
    assert parse_exclusion_reasons(["P-ABCDE=Timed out"]) == {"P-ABCDE": "Timed out"}
    with pytest.raises(AppError) as malformed:
        parse_exclusion_reasons(["P-ABCDE"])
    assert malformed.value.code == "PILOT_EXPORT_EXCLUSION_FORMAT"
