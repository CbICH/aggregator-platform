"""Private operations for the controlled human A/B pilot."""

import csv
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from secrets import token_hex, token_urlsafe

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.db import utcnow
from app.core.errors import AppError
from app.core.security import digest
from app.modules.assessment.models import (
    PilotAttempt,
    PilotEnrollment,
    PilotItem,
    PilotManualReview,
    PilotRun,
)
from app.modules.assessment.templates import FAMILIES, passes_assessment, score


def parse_exclusion_reasons(values: list[str]) -> dict[str, str]:
    exclusions: dict[str, str] = {}
    for value in values:
        code, separator, reason = value.partition("=")
        if not separator or not code.strip() or not reason.strip():
            raise AppError(
                422,
                "PILOT_EXPORT_EXCLUSION_FORMAT",
                "Исключение указывается как PARTICIPANT_CODE=причина",
            )
        code = code.strip()
        if code in exclusions:
            raise AppError(
                422,
                "PILOT_EXPORT_DUPLICATE_EXCLUSION",
                "Код участника нельзя исключить дважды",
            )
        exclusions[code] = reason.strip()
    return exclusions


def create_run(
    db: Session,
    specialization: str,
    target_grade: str,
    catalog_version: str,
    *,
    max_participants: int = 8,
) -> tuple[PilotRun, str]:
    if max_participants not in {6, 7, 8}:
        raise AppError(422, "PILOT_CAPACITY_INVALID", "Размер пилота должен быть от 6 до 8")
    invite_code = token_urlsafe(24)
    run = PilotRun(
        invite_code_hash=digest(invite_code),
        max_participants=max_participants,
        specialization=specialization,
        target_grade=target_grade,
        catalog_version=catalog_version,
        form_a_seed=token_hex(24),
        form_b_seed=token_hex(24),
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    return run, invite_code


def find_run_by_invite_code(db: Session, invite_code: str) -> PilotRun:
    run = db.scalar(select(PilotRun).where(PilotRun.invite_code_hash == digest(invite_code)))
    if run is None:
        raise AppError(404, "PILOT_INVITE_NOT_FOUND", "Приглашение в пилот не найдено")
    return run


def form_seed(run: PilotRun, form_code: str, template_id: str) -> str:
    source = run.form_a_seed if form_code == "A" else run.form_b_seed
    return hashlib.sha256(f"{source}:{template_id}".encode()).hexdigest()


def _locked_enrollment(db: Session, enrollment_id: str) -> PilotEnrollment:
    enrollment = db.scalar(
        select(PilotEnrollment).where(PilotEnrollment.id == enrollment_id).with_for_update()
    )
    if enrollment is None:
        raise AppError(404, "PILOT_PARTICIPANT_NOT_FOUND", "Участник пилота не найден")
    return enrollment


def _assert_manual_review_is_early(db: Session, enrollment: PilotEnrollment) -> None:
    if enrollment.manual_reviewed_at is not None:
        raise AppError(409, "PILOT_MANUAL_REVIEW_FINAL", "Ручная оценка уже зафиксирована")
    if db.scalar(select(PilotAttempt.id).where(PilotAttempt.enrollment_id == enrollment.id)):
        raise AppError(
            409,
            "PILOT_MANUAL_REVIEW_LATE",
            "Ручную оценку нельзя вносить после старта формы",
        )


def record_manual_review(
    db: Session, enrollment: PilotEnrollment, reviewer_code: str, assessed_grade: str
) -> PilotManualReview:
    """Persist one independent reviewer decision before any pilot form is opened."""
    code = reviewer_code.strip()
    if (
        len(code) < 3
        or len(code) > 64
        or any(not (character.isalnum() or character in "_-") for character in code)
    ):
        raise AppError(
            422,
            "PILOT_MANUAL_REVIEWER_CODE_INVALID",
            "Код рецензента содержит 3-64 символа: буквы, цифры, _ или -",
        )
    if assessed_grade not in {"junior", "middle", "senior"}:
        raise AppError(422, "PILOT_MANUAL_GRADE_INVALID", "Неизвестный ручной грейд")
    locked = _locked_enrollment(db, enrollment.id)
    _assert_manual_review_is_early(db, locked)
    existing = db.scalar(
        select(PilotManualReview).where(
            PilotManualReview.enrollment_id == locked.id,
            PilotManualReview.reviewer_code == code,
        )
    )
    if existing:
        raise AppError(
            409,
            "PILOT_MANUAL_REVIEW_DUPLICATE",
            "Рецензент уже зафиксировал независимую оценку",
        )
    review = PilotManualReview(
        enrollment_id=locked.id,
        reviewer_code=code,
        assessed_grade=assessed_grade,
    )
    db.add(review)
    db.commit()
    db.refresh(review)
    return review


def finalize_manual_review(
    db: Session,
    enrollment: PilotEnrollment,
    reviewer_count: int,
    resolved_grade: str | None = None,
    resolution_note: str = "",
) -> PilotEnrollment:
    """Make independently captured reviews usable without exposing them to the participant."""
    if reviewer_count not in {1, 2}:
        raise AppError(422, "PILOT_MANUAL_REVIEW_COUNT", "Нужен один эксперт или два рецензента")
    locked = _locked_enrollment(db, enrollment.id)
    _assert_manual_review_is_early(db, locked)
    reviews = db.scalars(
        select(PilotManualReview)
        .where(PilotManualReview.enrollment_id == locked.id)
        .order_by(PilotManualReview.recorded_at)
    ).all()
    if len(reviews) != reviewer_count:
        raise AppError(
            409,
            "PILOT_MANUAL_REVIEW_COUNT",
            "Число зафиксированных независимых оценок не совпадает с выбранным методом",
        )
    grades = {review.assessed_grade for review in reviews}
    note = resolution_note.strip()
    if len(grades) == 1:
        grade = next(iter(grades))
        if resolved_grade and resolved_grade != grade:
            raise AppError(
                422,
                "PILOT_MANUAL_REVIEW_CONSENSUS",
                "Итоговый грейд не совпадает с единогласной оценкой",
            )
        if note:
            raise AppError(
                422,
                "PILOT_MANUAL_REVIEW_NOTE_UNNEEDED",
                "Причина разрешения нужна только при расхождении оценок",
            )
        resolution = None
    else:
        if resolved_grade not in {"junior", "middle", "senior"} or len(note) < 10:
            raise AppError(
                422,
                "PILOT_MANUAL_REVIEW_DISAGREEMENT",
                "При расхождении укажите итоговый грейд и причину не короче 10 символов",
            )
        grade = resolved_grade
        resolution = note
    locked.manual_grade = grade
    locked.manual_reviewer_count = reviewer_count
    locked.manual_reviewed_at = utcnow()
    locked.manual_review_resolution = resolution
    db.commit()
    db.refresh(locked)
    return locked


def manual_review_is_complete(db: Session, enrollment: PilotEnrollment) -> bool:
    return bool(
        enrollment.manual_grade
        and enrollment.manual_reviewed_at
        and enrollment.manual_reviewer_count in {1, 2}
        and db.scalar(
            select(func.count())
            .select_from(PilotManualReview)
            .where(PilotManualReview.enrollment_id == enrollment.id)
        )
        == enrollment.manual_reviewer_count
    )


def review_enrollment(db: Session, enrollment: PilotEnrollment) -> list[PilotAttempt]:
    if not manual_review_is_complete(db, enrollment):
        raise AppError(409, "PILOT_MANUAL_REVIEW_REQUIRED", "Сначала зафиксируйте ручную оценку")
    attempts = db.scalars(
        select(PilotAttempt)
        .where(PilotAttempt.enrollment_id == enrollment.id)
        .order_by(PilotAttempt.sequence)
    ).all()
    if len(attempts) != 2 or any(
        attempt.status != "awaiting_manual_review" for attempt in attempts
    ):
        raise AppError(409, "PILOT_FORMS_INCOMPLETE", "Для проверки нужны две завершённые формы")
    run = db.get(PilotRun, enrollment.run_id)
    if run is None:
        raise AppError(404, "PILOT_RUN_NOT_FOUND", "Пилот не найден")
    for attempt in attempts:
        items = db.scalars(
            select(PilotItem).where(PilotItem.attempt_id == attempt.id).order_by(PilotItem.position)
        ).all()
        family_scores: dict[str, float] = {}
        for item in items:
            item.score = score(item.rubric, item.answers or {})
            family_scores[item.family] = item.score
        total = round(sum(family_scores.values()), 1)
        attempt.score = total
        attempt.family_scores = family_scores
        attempt.passed = passes_assessment(total, family_scores, FAMILIES[run.specialization][:2])
        attempt.status = "reviewed"
        attempt.reviewed_at = utcnow()
    db.commit()
    return attempts


def export_run(
    db: Session,
    run: PilotRun,
    csv_path: Path,
    metadata_path: Path,
    exclusion_reasons: dict[str, str],
    *,
    method: str,
) -> int:
    enrollments = db.scalars(
        select(PilotEnrollment)
        .where(PilotEnrollment.run_id == run.id)
        .order_by(PilotEnrollment.participant_code)
    ).all()
    excluded_codes = set(exclusion_reasons)
    known_codes = {enrollment.participant_code for enrollment in enrollments}
    unknown = excluded_codes - known_codes
    if unknown:
        raise AppError(
            422, "PILOT_EXPORT_UNKNOWN_EXCLUSION", f"Нет участника: {', '.join(sorted(unknown))}"
        )
    if any(not reason.strip() for reason in exclusion_reasons.values()):
        raise AppError(
            422,
            "PILOT_EXPORT_EXCLUSION_REASON_REQUIRED",
            "Для каждого исключения укажите причину",
        )
    rows: list[dict[str, str | int | float | bool]] = []
    dates: list[datetime] = []
    reviewer_counts: list[int] = []
    for enrollment in enrollments:
        attempts = db.scalars(
            select(PilotAttempt)
            .where(PilotAttempt.enrollment_id == enrollment.id)
            .order_by(PilotAttempt.form_code)
        ).all()
        completed = len(attempts) == 2 and all(attempt.status == "reviewed" for attempt in attempts)
        if enrollment.participant_code in excluded_codes:
            continue
        if not completed or not manual_review_is_complete(db, enrollment):
            raise AppError(
                409,
                "PILOT_EXPORT_INCOMPLETE",
                "Незавершённые наблюдения перечислите в --exclude",
                {"participant_code": enrollment.participant_code},
            )
        by_form = {attempt.form_code: attempt for attempt in attempts}
        first = min(attempts, key=lambda attempt: attempt.sequence)
        rows.append(
            {
                "participant_code": enrollment.participant_code,
                "specialization": run.specialization,
                "target_grade": run.target_grade,
                "form_order": "A-first" if first.form_code == "A" else "B-first",
                "manual_grade": enrollment.manual_grade,
                "score_a": by_form["A"].score or 0,
                "passed_a": bool(by_form["A"].passed),
                "duration_a_seconds": by_form["A"].duration_seconds or 0,
                "score_b": by_form["B"].score or 0,
                "passed_b": bool(by_form["B"].passed),
                "duration_b_seconds": by_form["B"].duration_seconds or 0,
                "notes": "",
            }
        )
        dates.extend(
            moment
            for attempt in attempts
            for moment in (attempt.started_at, attempt.submitted_at)
            if moment is not None
        )
        reviewer_counts.append(enrollment.manual_reviewer_count)
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with csv_path.open("w", encoding="utf-8", newline="") as target:
        writer = csv.DictWriter(
            target,
            fieldnames=(
                "participant_code",
                "specialization",
                "target_grade",
                "form_order",
                "manual_grade",
                "score_a",
                "passed_a",
                "duration_a_seconds",
                "score_b",
                "passed_b",
                "duration_b_seconds",
                "notes",
            ),
        )
        writer.writeheader()
        writer.writerows(rows)
    metadata = {
        "status": "measured" if rows else "not_measured",
        "collection_dates": (
            [
                min(dates).astimezone(UTC).date().isoformat(),
                max(dates).astimezone(UTC).date().isoformat(),
            ]
            if dates
            else []
        ),
        "template_versions": {
            "form_a": f"{run.catalog_version}:form-a",
            "form_b": f"{run.catalog_version}:form-b",
        },
        "manual_review": {
            "completed_before_automatic_scores": True,
            "reviewer_count": min(reviewer_counts) if reviewer_counts else 0,
            "method": method,
        },
        "excluded_participant_codes": sorted(excluded_codes),
        "exclusion_reasons": dict(sorted(exclusion_reasons.items())),
        "notes": "Exported by the controlled pilot operator command. Participant codes are pseudonyms.",
    }
    metadata_path.parent.mkdir(parents=True, exist_ok=True)
    metadata_path.write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return len(rows)
