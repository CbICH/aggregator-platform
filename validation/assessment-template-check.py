"""Produce a compact, reproducible B08 generator-validation report."""

import argparse
import json
from pathlib import Path

from app.modules.assessment.templates import (
    FAMILIES,
    TEMPLATES,
    build,
    passes_assessment,
    score,
    templates_for,
)

VARIANTS_PER_TEMPLATE = 100
TRANSFER_PAIRS_PER_CATEGORY = 20


def check_template(template) -> dict:
    scores: list[float] = []
    prompts: set[str] = set()
    for variant in range(VARIANTS_PER_TEMPLATE):
        prompt, rubric = build(template, f"validation-{template.id}-{variant}")
        prompts.add(json.dumps(prompt, ensure_ascii=False, sort_keys=True))
        answers = {rule["field"]: rule["expected"] for rule in rubric}
        result = score(rubric, answers)
        if result != template.weight:
            raise ValueError(
                f"{template.id} variant {variant} scored {result}, expected {template.weight}"
            )
        if "expected" in str(prompt) or "seed" in str(prompt).lower():
            raise ValueError(f"{template.id} variant {variant} leaks a private value")
        scores.append(result)
    if len(prompts) != VARIANTS_PER_TEMPLATE:
        raise ValueError(
            f"{template.id} generated {len(prompts)} distinct public variants, "
            f"expected {VARIANTS_PER_TEMPLATE}"
        )
    return {
        "template_id": template.id,
        "specialization": template.specialization,
        "grade": template.grade,
        "family": template.family,
        "variants_checked": VARIANTS_PER_TEMPLATE,
        "expected_weight": template.weight,
        "min_score": min(scores),
        "max_score": max(scores),
        "distinct_public_prompts": len(prompts),
        "public_prompt_leak": False,
    }


def rubric_answers(rubric: list[dict]) -> dict:
    return {rule["field"]: rule["expected"] for rule in rubric}


def check_copy_transfer(specialization: str, grade: str) -> dict:
    passed = 0
    for pair in range(TRANSFER_PAIRS_PER_CATEGORY):
        family_scores = {}
        for template in templates_for(specialization, grade):
            _, source_rubric = build(template, f"copy-source-{template.id}-{pair}")
            _, target_rubric = build(template, f"copy-target-{template.id}-{pair}")
            family_scores[template.family] = score(
                target_rubric, rubric_answers(source_rubric)
            )
        total = sum(family_scores.values())
        passed += passes_assessment(total, family_scores, FAMILIES[specialization][:2])
    return {
        "category": f"{specialization}:{grade}",
        "pairs_checked": TRANSFER_PAIRS_PER_CATEGORY,
        "copied_answer_passes": passed,
        "copied_answer_pass_rate": round(passed / TRANSFER_PAIRS_PER_CATEGORY, 4),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("validation/assessment-template-report.json"),
    )
    args = parser.parse_args()
    checks = [check_template(template) for template in TEMPLATES]
    transfers = [
        check_copy_transfer(specialization, grade)
        for specialization in FAMILIES
        for grade in ("junior", "middle", "senior")
    ]
    report = {
        "status": "passed",
        "templates_checked": len(checks),
        "variants_per_template": VARIANTS_PER_TEMPLATE,
        "total_variants_checked": len(checks) * VARIANTS_PER_TEMPLATE,
        "checks": checks,
        "copy_transfer_checks": transfers,
    }
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
