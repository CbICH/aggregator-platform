"""Operate the private human A/B pilot without exposing review data over HTTP."""

import argparse
from pathlib import Path

from sqlalchemy import select

from app.core.config import Settings
from app.core.db import make_engine, make_session_factory
from app.core.errors import AppError
from app.modules.assessment.models import PilotEnrollment
from app.modules.assessment.pilot import (
    create_run,
    export_run,
    finalize_manual_review,
    find_run_by_invite_code,
    parse_exclusion_reasons,
    record_manual_review,
    review_enrollment,
)

CATALOG_VERSION = "assessment-v1"


def enrollment_for(db, invite_code: str, participant_code: str) -> PilotEnrollment:
    run = find_run_by_invite_code(db, invite_code)
    enrollment = db.scalar(
        select(PilotEnrollment).where(
            PilotEnrollment.run_id == run.id,
            PilotEnrollment.participant_code == participant_code,
        )
    )
    if enrollment is None:
        raise AppError(404, "PILOT_PARTICIPANT_NOT_FOUND", "Участник пилота не найден")
    return enrollment


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description=__doc__)
    commands = root.add_subparsers(dest="command", required=True)
    create = commands.add_parser("create")
    create.add_argument("--specialization", choices=("backend", "qa"), required=True)
    create.add_argument("--target-grade", choices=("junior", "middle", "senior"), required=True)
    create.add_argument(
        "--max-participants",
        type=int,
        choices=(6, 7, 8),
        default=8,
        help="Planned controlled-pilot sample size; enrollment stops at this limit.",
    )
    record = commands.add_parser("record-manual-review")
    record.add_argument("--invite-code", required=True)
    record.add_argument("--participant-code", required=True)
    record.add_argument("--reviewer-code", required=True)
    record.add_argument("--manual-grade", choices=("junior", "middle", "senior"), required=True)
    finalize = commands.add_parser("finalize-manual-review")
    finalize.add_argument("--invite-code", required=True)
    finalize.add_argument("--participant-code", required=True)
    finalize.add_argument("--reviewer-count", type=int, choices=(1, 2), required=True)
    finalize.add_argument("--resolved-grade", choices=("junior", "middle", "senior"))
    finalize.add_argument("--resolution-note", default="")
    review = commands.add_parser("review")
    review.add_argument("--invite-code", required=True)
    review.add_argument("--participant-code", required=True)
    export = commands.add_parser("export")
    export.add_argument("--invite-code", required=True)
    export.add_argument("--csv", type=Path, required=True)
    export.add_argument("--metadata", type=Path, required=True)
    export.add_argument(
        "--exclude",
        action="append",
        default=[],
        metavar="PARTICIPANT_CODE=REASON",
        help="Repeat for every incomplete observation; a reason is mandatory.",
    )
    export.add_argument(
        "--manual-review-method",
        default="Independent expert or two team reviewers; recorded before automatic scoring.",
    )
    return root


def main() -> None:
    args = parser().parse_args()
    engine = make_engine(Settings().database_url)
    sessions = make_session_factory(engine)
    try:
        with sessions() as db:
            if args.command == "create":
                run, invite = create_run(
                    db,
                    args.specialization,
                    args.target_grade,
                    CATALOG_VERSION,
                    max_participants=args.max_participants,
                )
                print(f"pilot_run_id={run.id}")
                print(f"invite_code={invite}")
                print("Store the invite code securely; it is shown only by this create command.")
            elif args.command == "record-manual-review":
                enrollment = enrollment_for(db, args.invite_code, args.participant_code)
                review = record_manual_review(db, enrollment, args.reviewer_code, args.manual_grade)
                print(f"manual_review_recorded={review.reviewer_code}")
            elif args.command == "finalize-manual-review":
                enrollment = enrollment_for(db, args.invite_code, args.participant_code)
                finalized = finalize_manual_review(
                    db,
                    enrollment,
                    args.reviewer_count,
                    args.resolved_grade,
                    args.resolution_note,
                )
                print(f"manual_review_finalized={finalized.participant_code}")
            elif args.command == "review":
                enrollment = enrollment_for(db, args.invite_code, args.participant_code)
                reviewed = review_enrollment(db, enrollment)
                print("reviewed_forms=" + ",".join(attempt.form_code for attempt in reviewed))
            else:
                run = find_run_by_invite_code(db, args.invite_code)
                count = export_run(
                    db,
                    run,
                    args.csv,
                    args.metadata,
                    parse_exclusion_reasons(args.exclude),
                    method=args.manual_review_method,
                )
                print(f"exported_participants={count}")
    except AppError as error:
        raise SystemExit(f"{error.code}: {error.message}") from None
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
