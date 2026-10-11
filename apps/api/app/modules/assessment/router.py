from datetime import UTC, datetime, timedelta
from secrets import token_hex
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy import desc, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.contracts.schemas import (
    ActorContext,
    AssessmentAnswerUpdate,
    AssessmentHistory,
    AssessmentHistoryItem,
    AssessmentItemPublic,
    AssessmentQuestion,
    AssessmentResult,
    AssessmentStart,
    CategoryConfirm,
    CategoryHistory,
    CategoryHistoryItem,
    CategoryState,
    PilotAttemptPublic,
    PilotJoin,
    PilotProgress,
    PilotState,
    Role,
    SurveyCreate,
    SurveyHistory,
    SurveyResponse,
)
from app.core.db import get_db, utcnow
from app.core.errors import ERROR_RESPONSES, AppError
from app.core.models import User
from app.core.security import require_role
from app.modules.assessment.models import (
    AssessmentAttempt,
    AssessmentItem,
    GradeHistory,
    PilotAttempt,
    PilotEnrollment,
    PilotItem,
    PilotManualReview,
    PilotRun,
    SkillEvidenceRecord,
    Survey,
    VerifiedCategoryRecord,
)
from app.modules.assessment.pilot import find_run_by_invite_code, form_seed
from app.modules.assessment.read import to_verified_category
from app.modules.assessment.templates import (
    FAMILIES,
    GRADE_ORDER,
    SKILLS,
    WEIGHTS,
    build,
    passes_assessment,
    recommends_next_grade,
    score,
    templates_for,
)

router = APIRouter(tags=["Assessment"], responses=ERROR_RESPONSES)
Candidate = Annotated[ActorContext, Depends(require_role(Role.CANDIDATE))]
Db = Annotated[Session, Depends(get_db)]
CATALOG_VERSION = "assessment-v1"
ATTEMPT_DURATION = timedelta(minutes=25)
RESULT_TTL, RETRY_DELAY, CHANGE_COOLDOWN = (
    timedelta(days=7),
    timedelta(hours=24),
    timedelta(days=90),
)


def aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def find_attempt(db: Session, attempt_id: UUID, candidate_id: UUID) -> AssessmentAttempt:
    attempt = db.get(AssessmentAttempt, str(attempt_id))
    if attempt is None or attempt.candidate_id != str(candidate_id):
        raise AppError(404, "ASSESSMENT_NOT_FOUND", "Попытка недоступна")
    return attempt


def expire_if_needed(db: Session, attempt: AssessmentAttempt, now: datetime) -> bool:
    if attempt.status == "in_progress" and aware(attempt.deadline_at) <= now:
        attempt.status = "expired"
        db.commit()
        db.refresh(attempt)
    return attempt.status == "expired"


def public_item(item: AssessmentItem) -> AssessmentItemPublic:
    prompt = item.prompt
    return AssessmentItemPublic(
        id=item.id,
        position=item.position,
        family=item.family,
        title=prompt["title"],
        scenario=prompt["scenario"],
        questions=[AssessmentQuestion(**question) for question in prompt["questions"]],
        answers=item.answers or {},
    )


def public_result(
    db: Session, attempt: AssessmentAttempt, include_items: bool = True
) -> AssessmentResult:
    items = []
    if include_items:
        db_items = db.scalars(
            select(AssessmentItem)
            .where(AssessmentItem.attempt_id == attempt.id)
            .order_by(AssessmentItem.position)
        ).all()
        items = [public_item(item) for item in db_items]
    return AssessmentResult(
        id=attempt.id,
        specialization=attempt.specialization,
        target_grade=attempt.target_grade,
        status=attempt.status,
        started_at=aware(attempt.started_at),
        deadline_at=aware(attempt.deadline_at),
        submitted_at=aware(attempt.submitted_at) if attempt.submitted_at else None,
        score=attempt.score,
        family_scores=attempt.family_scores,
        passed=attempt.passed,
        next_grade_recommended=attempt.next_grade_recommended,
        items=items,
    )


def history_item(attempt: AssessmentAttempt) -> AssessmentHistoryItem:
    return AssessmentHistoryItem(
        id=attempt.id,
        specialization=attempt.specialization,
        target_grade=attempt.target_grade,
        status=attempt.status,
        started_at=aware(attempt.started_at),
        deadline_at=aware(attempt.deadline_at),
        submitted_at=aware(attempt.submitted_at) if attempt.submitted_at else None,
        score=attempt.score,
        passed=attempt.passed,
        next_grade_recommended=attempt.next_grade_recommended,
    )


def expire_pilot_if_needed(db: Session, attempt: PilotAttempt, now: datetime) -> bool:
    if attempt.status == "in_progress" and aware(attempt.deadline_at) <= now:
        attempt.status = "expired"
        db.commit()
        db.refresh(attempt)
    return attempt.status == "expired"


def public_pilot_attempt(
    db: Session, attempt: PilotAttempt, include_items: bool = True
) -> PilotAttemptPublic:
    items = []
    if include_items and attempt.status == "in_progress":
        stored = db.scalars(
            select(PilotItem).where(PilotItem.attempt_id == attempt.id).order_by(PilotItem.position)
        ).all()
        items = [public_item(item) for item in stored]
    return PilotAttemptPublic(
        id=attempt.id,
        form_code=attempt.form_code,
        sequence=attempt.sequence,
        status=attempt.status,
        started_at=aware(attempt.started_at),
        deadline_at=aware(attempt.deadline_at),
        submitted_at=aware(attempt.submitted_at) if attempt.submitted_at else None,
        items=items,
    )


def active_pilot_enrollment(
    db: Session, candidate_id: UUID
) -> tuple[PilotEnrollment, PilotRun] | None:
    return db.execute(
        select(PilotEnrollment, PilotRun)
        .join(PilotRun, PilotEnrollment.run_id == PilotRun.id)
        .where(PilotEnrollment.candidate_id == str(candidate_id), PilotRun.status == "open")
        .order_by(desc(PilotEnrollment.joined_at))
    ).first()


def pilot_state_for(
    db: Session, enrollment: PilotEnrollment | None, run: PilotRun | None
) -> PilotState:
    if enrollment is None or run is None:
        return PilotState(enrolled=False)
    attempts = db.scalars(
        select(PilotAttempt)
        .where(PilotAttempt.enrollment_id == enrollment.id)
        .order_by(PilotAttempt.sequence)
    ).all()
    for attempt in attempts:
        expire_pilot_if_needed(db, attempt, utcnow())
    current = next((attempt for attempt in attempts if attempt.status == "in_progress"), None)
    return PilotState(
        enrolled=True,
        participant_code=enrollment.participant_code,
        specialization=run.specialization,
        target_grade=run.target_grade,
        form_order=enrollment.form_order,
        manual_review_ready=enrollment.manual_grade is not None,
        attempts=[
            PilotProgress(
                form_code=attempt.form_code,
                sequence=attempt.sequence,
                status=attempt.status,
                submitted_at=aware(attempt.submitted_at) if attempt.submitted_at else None,
            )
            for attempt in attempts
        ],
        current_attempt=public_pilot_attempt(db, current) if current else None,
    )


def find_pilot_attempt(db: Session, attempt_id: UUID, candidate_id: UUID) -> PilotAttempt:
    attempt = db.scalar(
        select(PilotAttempt)
        .join(PilotEnrollment, PilotAttempt.enrollment_id == PilotEnrollment.id)
        .where(
            PilotAttempt.id == str(attempt_id), PilotEnrollment.candidate_id == str(candidate_id)
        )
    )
    if attempt is None:
        raise AppError(404, "PILOT_ATTEMPT_NOT_FOUND", "Пилотная попытка недоступна")
    return attempt


def validate_answers(items: list[AssessmentItem], payload: dict[str, dict]) -> dict[str, dict]:
    by_id = {item.id: item for item in items}
    if set(payload) - set(by_id):
        raise AppError(422, "ANSWER_INVALID", "В ответах есть неизвестное задание")
    clean: dict[str, dict] = {}
    for item_id, values in payload.items():
        if not isinstance(values, dict):
            raise AppError(422, "ANSWER_INVALID", "Ответ на задание должен быть объектом")
        questions = {q["name"]: q for q in by_id[item_id].prompt["questions"]}
        if set(values) - set(questions):
            raise AppError(422, "ANSWER_INVALID", "В ответах есть неизвестное поле")
        result: dict = {}
        for name, value in values.items():
            question = questions[name]
            choices = {choice["id"] for choice in question.get("choices", [])}
            if question["kind"] == "number":
                if not isinstance(value, int) or isinstance(value, bool):
                    raise AppError(422, "ANSWER_INVALID", "Числовой ответ должен быть целым")
            elif question["kind"] == "choice":
                if not isinstance(value, str) or value not in choices:
                    raise AppError(422, "ANSWER_INVALID", "Выберите вариант из задания")
            else:
                if (
                    not isinstance(value, list)
                    or len(value) != len(set(value))
                    or any(not isinstance(v, str) or v not in choices for v in value)
                ):
                    raise AppError(422, "ANSWER_INVALID", "Выберите уникальные варианты из задания")
                value = sorted(value)
            result[name] = value
        clean[item_id] = result
    return clean


@router.post("/candidate/surveys", response_model=SurveyResponse, status_code=201)
def create_survey(payload: SurveyCreate, actor: Candidate, db: Db):
    survey = Survey(
        candidate_id=str(actor.user_id), catalog_version=CATALOG_VERSION, **payload.model_dump()
    )
    db.add(survey)
    db.commit()
    db.refresh(survey)
    return SurveyResponse(
        id=survey.id,
        catalog_version=survey.catalog_version,
        created_at=aware(survey.created_at),
        **payload.model_dump(),
    )


@router.get("/candidate/surveys", response_model=SurveyHistory)
def list_surveys(actor: Candidate, db: Db):
    surveys = db.scalars(
        select(Survey)
        .where(Survey.candidate_id == str(actor.user_id))
        .order_by(desc(Survey.created_at))
    ).all()
    return SurveyHistory(
        items=[
            SurveyResponse(
                id=survey.id,
                industry=survey.industry,
                specialization=survey.specialization,
                declared_grade=survey.declared_grade,
                roles=survey.roles,
                experience_months=survey.experience_months,
                catalog_version=survey.catalog_version,
                created_at=aware(survey.created_at),
            )
            for survey in surveys
        ]
    )


@router.get("/candidate/pilot", response_model=PilotState)
def pilot_state(actor: Candidate, db: Db):
    enrollment = active_pilot_enrollment(db, actor.user_id)
    return pilot_state_for(db, *(enrollment or (None, None)))


@router.post("/candidate/pilot/join", response_model=PilotState, status_code=201)
def join_pilot(payload: PilotJoin, actor: Candidate, db: Db):
    run = find_run_by_invite_code(db, payload.invite_code)
    locked_run = db.scalar(select(PilotRun).where(PilotRun.id == run.id).with_for_update())
    if locked_run is None or locked_run.status != "open":
        raise AppError(409, "PILOT_CLOSED", "Набор в пилот завершён")
    db.scalar(select(User).where(User.id == str(actor.user_id)).with_for_update())
    active = active_pilot_enrollment(db, actor.user_id)
    if active:
        if active[0].run_id == locked_run.id:
            return pilot_state_for(db, *active)
        raise AppError(409, "PILOT_ALREADY_ENROLLED", "Сначала завершите текущий пилот")
    existing = db.scalar(
        select(PilotEnrollment).where(
            PilotEnrollment.run_id == locked_run.id,
            PilotEnrollment.candidate_id == str(actor.user_id),
        )
    )
    if existing:
        return pilot_state_for(db, existing, locked_run)
    enrollments = db.scalars(
        select(PilotEnrollment).where(PilotEnrollment.run_id == locked_run.id)
    ).all()
    if len(enrollments) >= locked_run.max_participants:
        raise AppError(
            409,
            "PILOT_CAPACITY_REACHED",
            "Набор в пилот завершён: достигнут запланированный размер выборки",
        )
    count_a = sum(enrollment.form_order == "A-first" for enrollment in enrollments)
    count_b = len(enrollments) - count_a
    enrollment = PilotEnrollment(
        run_id=locked_run.id,
        candidate_id=str(actor.user_id),
        participant_code=f"P-{token_hex(5).upper()}",
        form_order="A-first" if count_a <= count_b else "B-first",
    )
    db.add(enrollment)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        existing = db.scalar(
            select(PilotEnrollment).where(
                PilotEnrollment.run_id == locked_run.id,
                PilotEnrollment.candidate_id == str(actor.user_id),
            )
        )
        if existing:
            return pilot_state_for(db, existing, locked_run)
        raise
    db.refresh(enrollment)
    return pilot_state_for(db, enrollment, locked_run)


@router.post("/candidate/pilot/attempts", response_model=PilotAttemptPublic, status_code=201)
def start_pilot_attempt(actor: Candidate, db: Db):
    active = active_pilot_enrollment(db, actor.user_id)
    if active is None:
        raise AppError(404, "PILOT_NOT_ENROLLED", "Нет активного участия в пилоте")
    enrollment, run = active
    review_count = db.scalar(
        select(func.count())
        .select_from(PilotManualReview)
        .where(PilotManualReview.enrollment_id == enrollment.id)
    )
    if (
        enrollment.manual_grade is None
        or enrollment.manual_reviewed_at is None
        or enrollment.manual_reviewer_count not in {1, 2}
        or review_count != enrollment.manual_reviewer_count
    ):
        raise AppError(
            409,
            "PILOT_MANUAL_REVIEW_REQUIRED",
            "Ожидается независимая ручная оценка до начала форм",
        )
    attempts = db.scalars(
        select(PilotAttempt)
        .where(PilotAttempt.enrollment_id == enrollment.id)
        .order_by(PilotAttempt.sequence)
    ).all()
    now = utcnow()
    for attempt in attempts:
        if attempt.status == "in_progress" and not expire_pilot_if_needed(db, attempt, now):
            return public_pilot_attempt(db, attempt)
    if any(attempt.status == "expired" for attempt in attempts):
        raise AppError(
            409,
            "PILOT_FORM_EXPIRED",
            "Истёкшая пилотная форма не перезапускается; отметьте наблюдение у оператора",
        )
    if len(attempts) >= 2:
        raise AppError(409, "PILOT_FORMS_COMPLETE", "Обе пилотные формы уже отправлены")
    sequence = len(attempts) + 1
    order = ("A", "B") if enrollment.form_order == "A-first" else ("B", "A")
    form_code = order[sequence - 1]
    templates = templates_for(run.specialization, run.target_grade)
    if len(templates) != 3:
        raise AppError(409, "PILOT_UNAVAILABLE", "Для пилота нет полного набора заданий")
    attempt = PilotAttempt(
        enrollment_id=enrollment.id,
        form_code=form_code,
        sequence=sequence,
        deadline_at=now + ATTEMPT_DURATION,
    )
    db.add(attempt)
    db.flush()
    for position, template in enumerate(templates, start=1):
        seed = form_seed(run, form_code, template.id)
        prompt, rubric = build(template, seed)
        db.add(
            PilotItem(
                attempt_id=attempt.id,
                position=position,
                family=template.family,
                template_id=template.id,
                template_version="v1",
                private_seed=seed,
                prompt=prompt,
                rubric=rubric,
            )
        )
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        concurrent = db.scalar(
            select(PilotAttempt)
            .where(PilotAttempt.enrollment_id == enrollment.id, PilotAttempt.sequence == sequence)
            .order_by(desc(PilotAttempt.started_at))
        )
        if concurrent:
            return public_pilot_attempt(db, concurrent)
        raise
    db.refresh(attempt)
    return public_pilot_attempt(db, attempt)


@router.get("/candidate/pilot/attempts/{attempt_id}", response_model=PilotAttemptPublic)
def get_pilot_attempt(attempt_id: UUID, actor: Candidate, db: Db):
    attempt = find_pilot_attempt(db, attempt_id, actor.user_id)
    expire_pilot_if_needed(db, attempt, utcnow())
    return public_pilot_attempt(db, attempt)


@router.put("/candidate/pilot/attempts/{attempt_id}/answers", response_model=PilotAttemptPublic)
def save_pilot_answers(attempt_id: UUID, payload: AssessmentAnswerUpdate, actor: Candidate, db: Db):
    attempt = find_pilot_attempt(db, attempt_id, actor.user_id)
    if expire_pilot_if_needed(db, attempt, utcnow()):
        raise AppError(409, "PILOT_FORM_EXPIRED", "Время пилотной формы истекло")
    if attempt.status != "in_progress":
        raise AppError(409, "PILOT_FORM_FINAL", "Отправленную форму нельзя изменять")
    items = db.scalars(
        select(PilotItem).where(PilotItem.attempt_id == attempt.id).order_by(PilotItem.position)
    ).all()
    clean = validate_answers(items, payload.answers)
    for item in items:
        if item.id in clean:
            item.answers = clean[item.id]
    db.commit()
    return public_pilot_attempt(db, attempt)


@router.post("/candidate/pilot/attempts/{attempt_id}/submit", response_model=PilotAttemptPublic)
def submit_pilot_attempt(attempt_id: UUID, actor: Candidate, db: Db):
    attempt = find_pilot_attempt(db, attempt_id, actor.user_id)
    if attempt.status in {"awaiting_manual_review", "reviewed"}:
        return public_pilot_attempt(db, attempt, include_items=False)
    now = utcnow()
    if expire_pilot_if_needed(db, attempt, now):
        raise AppError(409, "PILOT_FORM_EXPIRED", "Время пилотной формы истекло")
    items = db.scalars(
        select(PilotItem).where(PilotItem.attempt_id == attempt.id).order_by(PilotItem.position)
    ).all()
    if any(
        set(question["name"] for question in item.prompt["questions"]) - set(item.answers or {})
        for item in items
    ):
        raise AppError(422, "PILOT_ANSWERS_INCOMPLETE", "Ответьте на все вопросы формы")
    attempt.status = "awaiting_manual_review"
    attempt.submitted_at = now
    attempt.duration_seconds = max(1, int((now - aware(attempt.started_at)).total_seconds()))
    db.commit()
    return public_pilot_attempt(db, attempt, include_items=False)


@router.post("/assessments", response_model=AssessmentResult, status_code=201)
def start_assessment(payload: AssessmentStart, actor: Candidate, db: Db):
    now, candidate_id = utcnow(), str(actor.user_id)
    # Serialize starts in PostgreSQL so the daily limit and active-target invariant survive races.
    db.scalar(select(User).where(User.id == candidate_id).with_for_update())
    verified = db.get(VerifiedCategoryRecord, candidate_id)
    if verified and aware(verified.next_change_at) > now:
        raise AppError(
            409,
            "GRADE_CHANGE_COOLDOWN",
            "Смена грейда пока недоступна",
            {"next_change_at": aware(verified.next_change_at).isoformat()},
        )
    if (
        verified
        and verified.specialization == payload.specialization
        and GRADE_ORDER[payload.target_grade] <= GRADE_ORDER[verified.verified_grade]
    ):
        raise AppError(409, "GRADE_NOT_ADVANCED", "Для смены категории выберите следующий уровень")
    active = db.scalar(
        select(AssessmentAttempt)
        .where(
            AssessmentAttempt.candidate_id == candidate_id,
            AssessmentAttempt.specialization == payload.specialization,
            AssessmentAttempt.target_grade == payload.target_grade,
            AssessmentAttempt.status == "in_progress",
        )
        .order_by(desc(AssessmentAttempt.started_at))
    )
    if active and not expire_if_needed(db, active, now):
        return public_result(db, active)
    starts = db.scalars(
        select(AssessmentAttempt).where(
            AssessmentAttempt.candidate_id == candidate_id,
            AssessmentAttempt.started_at >= now - timedelta(days=1),
        )
    ).all()
    if len(starts) >= 3:
        raise AppError(
            429, "ASSESSMENT_DAILY_LIMIT", "Доступно не более трёх оцениваемых стартов в сутки"
        )
    failed = db.scalar(
        select(AssessmentAttempt)
        .where(
            AssessmentAttempt.candidate_id == candidate_id,
            AssessmentAttempt.specialization == payload.specialization,
            AssessmentAttempt.target_grade == payload.target_grade,
            AssessmentAttempt.status == "failed",
        )
        .order_by(desc(AssessmentAttempt.submitted_at))
    )
    if failed and aware(failed.submitted_at or failed.started_at) + RETRY_DELAY > now:
        raise AppError(
            409, "ASSESSMENT_RETRY_COOLDOWN", "Повтор этого уровня доступен через 24 часа"
        )
    survey = db.scalar(
        select(Survey)
        .where(Survey.candidate_id == candidate_id, Survey.specialization == payload.specialization)
        .order_by(desc(Survey.created_at))
    )
    if survey is None:
        raise AppError(
            409,
            "SURVEY_REQUIRED",
            "Сначала заполните обязательный опрос для выбранной специализации",
        )
    templates = templates_for(payload.specialization, payload.target_grade)
    if len(templates) != 3:
        raise AppError(409, "ASSESSMENT_UNAVAILABLE", "Тест для этой категории пока недоступен")
    attempt = AssessmentAttempt(
        candidate_id=candidate_id,
        survey_id=survey.id,
        survey_snapshot={
            "industry": survey.industry,
            "specialization": survey.specialization,
            "declared_grade": survey.declared_grade,
            "roles": survey.roles,
            "experience_months": survey.experience_months,
            "catalog_version": survey.catalog_version,
            "created_at": aware(survey.created_at).isoformat(),
        },
        specialization=payload.specialization,
        target_grade=payload.target_grade,
        catalog_version=CATALOG_VERSION,
        deadline_at=now + ATTEMPT_DURATION,
    )
    db.add(attempt)
    db.flush()
    for position, template in enumerate(templates, start=1):
        seed = token_hex(24)
        prompt, rubric = build(template, seed)
        db.add(
            AssessmentItem(
                attempt_id=attempt.id,
                position=position,
                family=template.family,
                template_id=template.id,
                template_version="v1",
                private_seed=seed,
                prompt=prompt,
                rubric=rubric,
            )
        )
    try:
        db.commit()
    except IntegrityError:
        # A concurrent request may have created this candidate's active target after our read.
        db.rollback()
        concurrent = db.scalar(
            select(AssessmentAttempt)
            .where(
                AssessmentAttempt.candidate_id == candidate_id,
                AssessmentAttempt.specialization == payload.specialization,
                AssessmentAttempt.target_grade == payload.target_grade,
                AssessmentAttempt.status == "in_progress",
            )
            .order_by(desc(AssessmentAttempt.started_at))
        )
        if concurrent:
            return public_result(db, concurrent)
        raise
    db.refresh(attempt)
    return public_result(db, attempt)


@router.get("/assessments/{assessment_id}", response_model=AssessmentResult)
def get_assessment(assessment_id: UUID, actor: Candidate, db: Db):
    attempt = find_attempt(db, assessment_id, actor.user_id)
    expire_if_needed(db, attempt, utcnow())
    return public_result(db, attempt)


@router.put("/assessments/{assessment_id}/answers", response_model=AssessmentResult)
def save_answers(assessment_id: UUID, payload: AssessmentAnswerUpdate, actor: Candidate, db: Db):
    attempt = find_attempt(db, assessment_id, actor.user_id)
    if expire_if_needed(db, attempt, utcnow()):
        raise AppError(409, "ASSESSMENT_EXPIRED", "Время попытки истекло")
    if attempt.status != "in_progress":
        raise AppError(409, "ASSESSMENT_FINAL", "Финальная попытка больше не редактируется")
    items = db.scalars(select(AssessmentItem).where(AssessmentItem.attempt_id == attempt.id)).all()
    clean = validate_answers(items, payload.answers)
    for item in items:
        if item.id in clean:
            item.answers = clean[item.id]
    db.commit()
    return public_result(db, attempt)


@router.post("/assessments/{assessment_id}/submit", response_model=AssessmentResult)
def submit_assessment(assessment_id: UUID, actor: Candidate, db: Db):
    attempt = find_attempt(db, assessment_id, actor.user_id)
    if attempt.status in {"passed", "failed"}:
        return public_result(db, attempt)
    if expire_if_needed(db, attempt, utcnow()):
        raise AppError(409, "ASSESSMENT_EXPIRED", "Время попытки истекло")
    items = db.scalars(
        select(AssessmentItem)
        .where(AssessmentItem.attempt_id == attempt.id)
        .order_by(AssessmentItem.position)
    ).all()
    family_scores: dict[str, float] = {}
    for item in items:
        item.score = score(item.rubric, item.answers or {})
        family_scores[item.family] = item.score
    total = round(sum(family_scores.values()), 1)
    passed = passes_assessment(total, family_scores, FAMILIES[attempt.specialization][:2])
    attempt.score, attempt.family_scores, attempt.passed = total, family_scores, passed
    attempt.next_grade_recommended = (
        recommends_next_grade(total) and GRADE_ORDER[attempt.target_grade] < 2
    )
    attempt.status, attempt.submitted_at = ("passed" if passed else "failed"), utcnow()
    db.commit()
    return public_result(db, attempt)


@router.get("/candidate/assessments", response_model=AssessmentHistory)
def list_assessments(actor: Candidate, db: Db):
    attempts = db.scalars(
        select(AssessmentAttempt)
        .where(AssessmentAttempt.candidate_id == str(actor.user_id))
        .order_by(desc(AssessmentAttempt.started_at))
    ).all()
    for attempt in attempts:
        expire_if_needed(db, attempt, utcnow())
    return AssessmentHistory(items=[history_item(item) for item in attempts])


@router.get("/candidate/category", response_model=CategoryState)
def category_state(actor: Candidate, db: Db):
    current = db.get(VerifiedCategoryRecord, str(actor.user_id))
    provisional = db.scalar(
        select(AssessmentAttempt)
        .where(
            AssessmentAttempt.candidate_id == str(actor.user_id),
            AssessmentAttempt.status == "passed",
        )
        .order_by(desc(AssessmentAttempt.submitted_at))
    )
    if current and provisional and provisional.id == current.assessment_id:
        provisional = None
    return CategoryState(
        verified=to_verified_category(db, current) if current else None,
        provisional=history_item(provisional) if provisional else None,
    )


@router.get("/candidate/category/history", response_model=CategoryHistory)
def category_history(actor: Candidate, db: Db):
    history = db.scalars(
        select(GradeHistory)
        .where(GradeHistory.candidate_id == str(actor.user_id))
        .order_by(desc(GradeHistory.assigned_at))
    ).all()
    return CategoryHistory(
        items=[
            CategoryHistoryItem(
                assessment_id=item.assessment_id,
                category_code=item.category_code,
                assigned_at=aware(item.assigned_at),
                next_change_at=aware(item.next_change_at),
            )
            for item in history
        ]
    )


@router.post("/candidate/category/confirm", response_model=CategoryState)
def confirm_category(payload: CategoryConfirm, actor: Candidate, db: Db):
    now, candidate_id = utcnow(), str(actor.user_id)
    # PostgreSQL locks the candidate identity here; the current category and history are then changed together.
    db.scalar(select(User).where(User.id == candidate_id).with_for_update())
    attempt = find_attempt(db, payload.assessment_id, actor.user_id)
    if attempt.status != "passed" or not attempt.passed:
        raise AppError(
            409, "ASSESSMENT_NOT_PASSED", "Подтвердить можно только успешно завершённый тест"
        )
    if aware(attempt.submitted_at or attempt.started_at) + RESULT_TTL < now:
        raise AppError(409, "ASSESSMENT_RESULT_EXPIRED", "Результат устарел, пройдите новый тест")
    current = db.get(VerifiedCategoryRecord, candidate_id)
    if current and current.assessment_id == attempt.id:
        return CategoryState(verified=to_verified_category(db, current))
    if current and aware(current.next_change_at) > now:
        raise AppError(409, "GRADE_CHANGE_COOLDOWN", "Смена грейда пока недоступна")
    if (
        current
        and current.specialization == attempt.specialization
        and GRADE_ORDER[attempt.target_grade] <= GRADE_ORDER[current.verified_grade]
    ):
        raise AppError(409, "GRADE_NOT_ADVANCED", "Подтверждённый грейд нельзя понизить")
    category_code, version, next_change = (
        f"{attempt.specialization}:{attempt.target_grade}",
        f"{attempt.specialization}-{attempt.target_grade}-v1",
        now + CHANGE_COOLDOWN,
    )
    if current:
        current.category_code, current.specialization, current.verified_grade = (
            category_code,
            attempt.specialization,
            attempt.target_grade,
        )
        current.test_score, current.assessment_id, current.assessment_version = (
            attempt.score or 0,
            attempt.id,
            version,
        )
        current.assigned_at, current.next_change_at = now, next_change
        record = current
    else:
        record = VerifiedCategoryRecord(
            candidate_id=candidate_id,
            category_code=category_code,
            specialization=attempt.specialization,
            verified_grade=attempt.target_grade,
            test_score=attempt.score or 0,
            assessment_id=attempt.id,
            assessment_version=version,
            assigned_at=now,
            next_change_at=next_change,
        )
        db.add(record)
    db.add(
        GradeHistory(
            candidate_id=candidate_id,
            assessment_id=attempt.id,
            category_code=category_code,
            assigned_at=now,
            next_change_at=next_change,
        )
    )
    for item in db.scalars(
        select(AssessmentItem).where(AssessmentItem.attempt_id == attempt.id)
    ).all():
        normalized = round(100 * (item.score or 0) / WEIGHTS[item.family], 1)
        for skill_id in SKILLS[item.family]:
            db.add(
                SkillEvidenceRecord(
                    candidate_id=candidate_id,
                    assessment_id=attempt.id,
                    skill_id=skill_id,
                    score=normalized,
                    assessment_version=version,
                )
            )
    db.commit()
    db.refresh(record)
    return CategoryState(verified=to_verified_category(db, record))
