"""Calculate reproducible pilot metrics from the anonymized raw-results CSV."""

import argparse
import csv
import json
import statistics
from collections import Counter
from pathlib import Path

GRADE_ORDER = {"junior": 0, "middle": 1, "senior": 2}
SPECIALIZATIONS = {"backend", "qa"}
FORM_ORDERS = {"A-first", "B-first"}
REQUIRED_COLUMNS = (
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
)
REQUIRED_METADATA_KEYS = {
    "status",
    "collection_dates",
    "template_versions",
    "manual_review",
    "excluded_participant_codes",
    "exclusion_reasons",
    "notes",
}


def parse_bool(value: str, *, field: str, row_number: int) -> bool:
    normalized = value.strip().lower()
    if normalized == "true":
        return True
    if normalized == "false":
        return False
    raise ValueError(f"row {row_number}: {field} must be true or false")


def parse_score(value: str, *, field: str, row_number: int) -> float:
    try:
        score = float(value)
    except ValueError as error:
        raise ValueError(f"row {row_number}: {field} must be a number") from error
    if not 0 <= score <= 100:
        raise ValueError(f"row {row_number}: {field} must be between 0 and 100")
    return score


def parse_duration(value: str, *, field: str, row_number: int) -> int:
    try:
        duration = int(value)
    except ValueError as error:
        raise ValueError(f"row {row_number}: {field} must be an integer") from error
    if duration <= 0:
        raise ValueError(f"row {row_number}: {field} must be positive")
    return duration


def read_rows(path: Path, excluded_codes: set[str]) -> tuple[list[dict], list[str]]:
    with path.open(encoding="utf-8-sig", newline="") as source:
        reader = csv.DictReader(source)
        if tuple(reader.fieldnames or ()) != REQUIRED_COLUMNS:
            raise ValueError(
                "CSV columns do not match the published raw-results template"
            )
        rows: list[dict] = []
        excluded_seen: list[str] = []
        participant_codes: set[str] = set()
        for row_number, raw in enumerate(reader, start=2):
            code = raw["participant_code"].strip()
            if not code:
                raise ValueError(f"row {row_number}: participant_code is required")
            if code in participant_codes:
                raise ValueError(f"row {row_number}: duplicate participant_code {code}")
            participant_codes.add(code)
            if code in excluded_codes:
                excluded_seen.append(code)
                continue
            specialization = raw["specialization"].strip()
            target_grade = raw["target_grade"].strip()
            manual_grade = raw["manual_grade"].strip()
            form_order = raw["form_order"].strip()
            if specialization not in SPECIALIZATIONS:
                raise ValueError(f"row {row_number}: unsupported specialization")
            if target_grade not in GRADE_ORDER or manual_grade not in GRADE_ORDER:
                raise ValueError(f"row {row_number}: unsupported grade")
            if form_order not in FORM_ORDERS:
                raise ValueError(
                    f"row {row_number}: form_order must be A-first or B-first"
                )
            rows.append(
                {
                    "participant_code": code,
                    "specialization": specialization,
                    "target_grade": target_grade,
                    "form_order": form_order,
                    "manual_grade": manual_grade,
                    "score_a": parse_score(
                        raw["score_a"], field="score_a", row_number=row_number
                    ),
                    "passed_a": parse_bool(
                        raw["passed_a"], field="passed_a", row_number=row_number
                    ),
                    "duration_a_seconds": parse_duration(
                        raw["duration_a_seconds"],
                        field="duration_a_seconds",
                        row_number=row_number,
                    ),
                    "score_b": parse_score(
                        raw["score_b"], field="score_b", row_number=row_number
                    ),
                    "passed_b": parse_bool(
                        raw["passed_b"], field="passed_b", row_number=row_number
                    ),
                    "duration_b_seconds": parse_duration(
                        raw["duration_b_seconds"],
                        field="duration_b_seconds",
                        row_number=row_number,
                    ),
                }
            )
    missing_exclusions = excluded_codes - set(excluded_seen)
    if missing_exclusions:
        raise ValueError(
            f"metadata excludes codes absent from CSV: {', '.join(sorted(missing_exclusions))}"
        )
    return rows, excluded_seen


def read_metadata(path: Path) -> dict:
    metadata = json.loads(path.read_text(encoding="utf-8"))
    if set(metadata) != REQUIRED_METADATA_KEYS:
        raise ValueError("metadata keys do not match the published pilot template")
    if metadata["status"] not in {"not_measured", "measured"}:
        raise ValueError("metadata.status must be not_measured or measured")
    if not isinstance(metadata["excluded_participant_codes"], list) or any(
        not isinstance(code, str) or not code
        for code in metadata["excluded_participant_codes"]
    ):
        raise ValueError(
            "metadata.excluded_participant_codes must be a list of non-empty codes"
        )
    if len(metadata["excluded_participant_codes"]) != len(
        set(metadata["excluded_participant_codes"])
    ):
        raise ValueError(
            "metadata.excluded_participant_codes must not contain duplicates"
        )
    if (
        not isinstance(metadata["exclusion_reasons"], dict)
        or set(metadata["exclusion_reasons"]) != set(metadata["excluded_participant_codes"])
        or any(
            not isinstance(reason, str) or not reason.strip()
            for reason in metadata["exclusion_reasons"].values()
        )
    ):
        raise ValueError(
            "metadata.exclusion_reasons must contain one non-empty reason per excluded code"
        )
    if not isinstance(metadata["template_versions"], dict) or set(
        metadata["template_versions"]
    ) != {
        "form_a",
        "form_b",
    }:
        raise ValueError("metadata.template_versions must contain form_a and form_b")
    manual_review = metadata["manual_review"]
    if (
        not isinstance(manual_review, dict)
        or set(manual_review)
        != {"completed_before_automatic_scores", "reviewer_count", "method"}
        or not isinstance(manual_review["completed_before_automatic_scores"], bool)
        or not isinstance(manual_review["reviewer_count"], int)
        or manual_review["reviewer_count"] < 0
        or not isinstance(manual_review["method"], str)
    ):
        raise ValueError("metadata.manual_review does not match the published pilot template")
    if metadata["status"] == "measured" and (
        not manual_review["completed_before_automatic_scores"]
        or manual_review["reviewer_count"] not in {1, 2}
        or not manual_review["method"].strip()
    ):
        raise ValueError("measured pilot requires a documented independent manual review")
    return metadata


def describe(values: list[float | int]) -> dict[str, float | int | None]:
    if not values:
        return {"count": 0, "mean": None, "median": None, "min": None, "max": None}
    return {
        "count": len(values),
        "mean": round(statistics.fmean(values), 2),
        "median": round(statistics.median(values), 2),
        "min": min(values),
        "max": max(values),
    }


def agreement(rows: list[dict], form: str) -> dict[str, float | int | None]:
    if not rows:
        return {
            "count": 0,
            "matches": 0,
            "rate": None,
            "false_positive": 0,
            "false_negative": 0,
        }
    matches = false_positive = false_negative = 0
    for row in rows:
        expected = GRADE_ORDER[row["manual_grade"]] >= GRADE_ORDER[row["target_grade"]]
        actual = row[f"passed_{form}"]
        matches += actual == expected
        false_positive += actual and not expected
        false_negative += expected and not actual
    return {
        "count": len(rows),
        "matches": matches,
        "rate": round(matches / len(rows), 4),
        "false_positive": false_positive,
        "false_negative": false_negative,
    }


def score_delta(rows: list[dict]) -> dict[str, float | int | None]:
    deltas = [abs(row["score_a"] - row["score_b"]) for row in rows]
    if not deltas:
        return {
            "count": 0,
            "median_absolute_difference": None,
            "max_absolute_difference": None,
        }
    return {
        "count": len(deltas),
        "median_absolute_difference": round(statistics.median(deltas), 2),
        "max_absolute_difference": max(deltas),
    }


def decision_agreement(rows: list[dict]) -> dict[str, float | int | None]:
    if not rows:
        return {"count": 0, "matches": 0, "rate": None}
    matches = sum(row["passed_a"] == row["passed_b"] for row in rows)
    return {
        "count": len(rows),
        "matches": matches,
        "rate": round(matches / len(rows), 4),
    }


def near_threshold(rows: list[dict]) -> list[dict]:
    return [
        {
            "participant_code": row["participant_code"],
            "score_a": row["score_a"],
            "score_b": row["score_b"],
            "passed_a": row["passed_a"],
            "passed_b": row["passed_b"],
        }
        for row in rows
        if 60 <= row["score_a"] <= 80 or 60 <= row["score_b"] <= 80
    ]


def discrimination(
    rows: list[dict], form: str
) -> dict[str, dict[str, float | int | None]]:
    strong = [
        row[f"score_{form}"]
        for row in rows
        if GRADE_ORDER[row["manual_grade"]] >= GRADE_ORDER[row["target_grade"]]
    ]
    weak = [
        row[f"score_{form}"]
        for row in rows
        if GRADE_ORDER[row["manual_grade"]] < GRADE_ORDER[row["target_grade"]]
    ]
    return {
        "stronger_or_equal_manual_group": describe(strong),
        "weaker_manual_group": describe(weak),
        "mean_score_difference": round(
            statistics.fmean(strong) - statistics.fmean(weak), 2
        )
        if strong and weak
        else None,
    }


def protocol_checks(rows: list[dict], metadata: dict) -> dict:
    """State protocol checks without treating planned targets as measured results."""
    order_counts = Counter(row["form_order"] for row in rows)
    sample_size = len(rows)
    median_delta = score_delta(rows)["median_absolute_difference"]
    decision_rate = decision_agreement(rows)["rate"]
    return {
        "sample_size": {
            "actual": sample_size,
            "minimum": 6,
            "maximum": 8,
            "within_planned_range": 6 <= sample_size <= 8,
        },
        "form_order_balance": {
            "a_first": order_counts["A-first"],
            "b_first": order_counts["B-first"],
            "difference": abs(order_counts["A-first"] - order_counts["B-first"]),
            # A sample of seven cannot split exactly in half.
            "balanced": abs(order_counts["A-first"] - order_counts["B-first"]) <= 1,
        },
        "manual_review_before_scoring": {
            "completed": metadata["manual_review"]["completed_before_automatic_scores"],
            "reviewer_count": metadata["manual_review"]["reviewer_count"],
        },
        "score_stability": {
            "median_absolute_difference": median_delta,
            "target_maximum": 10,
            "meets_orientation": median_delta is not None and median_delta <= 10,
        },
        "decision_stability": {
            "agreement_rate": decision_rate,
            "target_minimum": 0.8,
            "meets_orientation": decision_rate is not None and decision_rate >= 0.8,
        },
    }


def analyze(rows: list[dict], metadata: dict, excluded_rows: list[str]) -> dict:
    status = "measured" if rows else "not_measured"
    if rows and metadata["status"] != "measured":
        raise ValueError(
            "metadata.status must be measured when raw pilot rows are present"
        )
    if not rows and metadata["status"] != "not_measured":
        raise ValueError(
            "metadata.status must be not_measured when raw pilot rows are absent"
        )
    report = {
        "status": status,
        "sample_size": len(rows),
        "metadata": {
            "collection_dates": metadata["collection_dates"],
            "template_versions": metadata["template_versions"],
            "manual_review": metadata["manual_review"],
            "excluded_participant_codes": excluded_rows,
            "exclusion_reasons": metadata["exclusion_reasons"],
        },
        "form_order": dict(sorted(Counter(row["form_order"] for row in rows).items())),
        "score_a": describe([row["score_a"] for row in rows]),
        "score_b": describe([row["score_b"] for row in rows]),
        "duration_a_seconds": describe([row["duration_a_seconds"] for row in rows]),
        "duration_b_seconds": describe([row["duration_b_seconds"] for row in rows]),
        "pass_rate_a": round(sum(row["passed_a"] for row in rows) / len(rows), 4)
        if rows
        else None,
        "pass_rate_b": round(sum(row["passed_b"] for row in rows) / len(rows), 4)
        if rows
        else None,
        "manual_agreement_a": agreement(rows, "a"),
        "manual_agreement_b": agreement(rows, "b"),
        "a_b_score_difference": score_delta(rows),
        "a_b_decision_agreement": decision_agreement(rows),
        "near_threshold_observations": near_threshold(rows),
        "discrimination_a": discrimination(rows, "a"),
        "discrimination_b": discrimination(rows, "b"),
        "protocol_checks": protocol_checks(rows, metadata),
        "limitations": [
            "Volunteer sampling does not represent the whole market.",
            "The protocol cannot prove the absence of outside assistance.",
        ],
    }
    if len(rows) < 6:
        report["limitations"].append(
            "Sample is smaller than the planned minimum of six people."
        )
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=Path("raw_results.csv"))
    parser.add_argument("--metadata", type=Path, default=Path("metadata.json"))
    parser.add_argument("--output", type=Path, default=Path("report.json"))
    args = parser.parse_args()
    metadata = read_metadata(args.metadata)
    rows, excluded_rows = read_rows(
        args.input, set(metadata["excluded_participant_codes"])
    )
    report = analyze(rows, metadata, excluded_rows)
    args.output.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
