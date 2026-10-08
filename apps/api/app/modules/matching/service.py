"""Логика подборки кандидатов для работодателя.

Формула (из плана):
  - без потребности:   score = 0.90 * T + 0.10 * F
  - с потребностью:    score = 0.65 * T + 0.25 * R + 0.10 * F

где T — балл теста (0..100), R — взвешенное соответствие проверенных навыков
требуемым (0..100), F — сигнал ФСП (0..100, нормированный).

Источник ФСП абстрагирован через `app.modules.fsp.provider.FspProvider`
(port/adapter). Сейчас это DemoFspProvider (данные из фикстур), в проде
подменяется на HttpFspProvider — формула и сервис не меняются.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from app.modules.fsp.provider import DemoFspProvider, FspProvider, FspSignal
from app.modules.matching import fixtures

# --- Веса компонент --------------------------------------------------------

WEIGHT_TEST_NO_NEED = 0.90
WEIGHT_FSP_NO_NEED = 0.10

WEIGHT_TEST_WITH_NEED = 0.65
WEIGHT_RELEVANCE_WITH_NEED = 0.25
WEIGHT_FSP_WITH_NEED = 0.10

# --- Нормализация результата соревнования → балл 0..100 --------------------

FSP_SIGNAL_BY_RESULT: dict[str, int] = {
    "участник": 30,
    "финалист": 60,
    "призовое место": 85,
    "призёр": 85,
    "победитель": 100,
}

# --- Фолбэк на дефолтного провайдера --------------------------------------
# Если роутер не передал провайдер явно (например, в юнит-тесте сервиса) —
# берём DemoFspProvider. В проде app.state.fsp_provider всегда задан.

_default_fsp_provider: FspProvider | None = None


def _default_provider() -> FspProvider:
    global _default_fsp_provider
    if _default_fsp_provider is None:
        _default_fsp_provider = DemoFspProvider()
    return _default_fsp_provider


@dataclass
class RankedCandidate:
    candidate: dict[str, Any]
    score: float
    components: dict[str, float]  # {"test", "relevance"?, "fsp"}
    reasons: list[dict[str, Any]]
    fsp_signal: FspSignal


# --- Вспомогательные расчёты -----------------------------------------------


def fsp_score(signal: FspSignal) -> float:
    """F = нормированный балл ФСП из статуса + лучшего достижения."""
    if signal.status != "linked_with_data":
        return 0.0
    best = 0
    for a in signal.achievements:
        value = FSP_SIGNAL_BY_RESULT.get(a.result.lower(), 0)
        if value > best:
            best = value
    return float(best)


def relevance(
    candidate: dict[str, Any],
    required_skills: list[dict[str, Any]],
) -> tuple[float, dict[str, Any]]:
    """R = sum(weight_i * confirmed_score_i) / sum(weight_i), 0..100.

    Непроверенный требуемый навык даёт 0, но отдельно помечается — не как
    «кандидат не умеет», а как «не проверено тестом».
    """
    if not required_skills:
        return 0.0, {"covered": [], "not_assessed": []}

    confirmed = {s["id"]: float(s["score"]) for s in candidate.get("skills", [])}
    total_weight = sum(r["weight"] for r in required_skills)
    if total_weight <= 0:
        return 0.0, {"covered": [], "not_assessed": []}

    weighted = 0.0
    covered: list[dict[str, Any]] = []
    not_assessed: list[str] = []
    for req in required_skills:
        weight = req["weight"]
        if req["id"] in confirmed:
            score = confirmed[req["id"]]
            weighted += weight * score
            covered.append({"id": req["id"], "score": score, "weight": weight})
        else:
            not_assessed.append(req["id"])
    return weighted / total_weight, {"covered": covered, "not_assessed": not_assessed}


def compute_reasons(
    candidate: dict[str, Any],
    signal: FspSignal,
    *,
    coverage: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    reasons: list[dict[str, Any]] = []
    verified_grade = candidate.get("verified_grade")
    if verified_grade:
        reasons.append({"code": "GRADE_VERIFIED", "label": f"{verified_grade.title()} подтверждён тестом"})

    if coverage:
        for match in coverage.get("covered", []):
            reasons.append({
                "code": "SKILL_MATCH",
                "skill_id": match["id"],
                "score": match["score"],
            })
        for skill_id in coverage.get("not_assessed", []):
            reasons.append({
                "code": "SKILL_NOT_ASSESSED",
                "skill_id": skill_id,
                "label": f"{skill_id} не проверялся в тесте",
            })
    else:
        for skill in candidate.get("skills", []):
            reasons.append({"code": "SKILL", "skill_id": skill["id"], "score": skill["score"]})

    if signal.status == "linked_with_data" and signal.achievements:
        top = max(
            signal.achievements,
            key=lambda a: FSP_SIGNAL_BY_RESULT.get(a.result.lower(), 0),
        )
        reasons.append({
            "code": "FSP_SIGNAL",
            "label": f"{top.result.capitalize()}: {top.event}",
            "date": top.date,
        })
    elif signal.status == "unavailable":
        reasons.append({"code": "FSP_UNAVAILABLE", "label": "Статус ФСП временно недоступен"})
    return reasons


# --- Основной API сервиса --------------------------------------------------


def rank_candidates(
    *,
    specialization: str | None = None,
    grade: Literal["junior", "middle", "senior"] | None = None,
    with_fsp_only: bool = False,
    need: dict[str, Any] | None = None,
    fsp_provider: FspProvider | None = None,
) -> list[RankedCandidate]:
    """Отсортированный список кандидатов.

    `fsp_provider` — внешний источник сигнала ФСП (port/adapter).
    Если не передан, используется DemoFspProvider как фолбэк.
    """
    provider = fsp_provider or _default_provider()
    pool = fixtures.visible_candidates()

    # Потребность задаёт жёсткий фильтр по специализации и грейдам.
    if need:
        pool = [c for c in pool if c.get("specialization") == need["specialization"]]
        if need.get("grades"):
            pool = [c for c in pool if c.get("verified_grade") in need["grades"]]
    else:
        if specialization:
            pool = [c for c in pool if c.get("specialization") == specialization]
        if grade:
            pool = [c for c in pool if c.get("verified_grade") == grade]

    required_skills = need.get("required_skills", []) if need else []
    ranked: list[RankedCandidate] = []

    for candidate in pool:
        signal = provider.get_signal(candidate["candidate_id"])

        # Фильтр «только с ФСП» применяется после запроса в провайдер —
        # статус знает только он, не фикстура.
        if with_fsp_only and signal.status != "linked_with_data":
            continue

        test_score = float(candidate.get("assessment", {}).get("test_score", 0))
        fsp = fsp_score(signal)

        if need and required_skills:
            r_score, coverage = relevance(candidate, required_skills)
            score = round(
                WEIGHT_TEST_WITH_NEED * test_score
                + WEIGHT_RELEVANCE_WITH_NEED * r_score
                + WEIGHT_FSP_WITH_NEED * fsp,
                1,
            )
            components = {"test": test_score, "relevance": r_score, "fsp": fsp}
            reasons = compute_reasons(candidate, signal, coverage=coverage)
        else:
            score = round(WEIGHT_TEST_NO_NEED * test_score + WEIGHT_FSP_NO_NEED * fsp, 1)
            components = {"test": test_score, "fsp": fsp}
            reasons = compute_reasons(candidate, signal)

        ranked.append(RankedCandidate(
            candidate=candidate,
            score=score,
            components=components,
            reasons=reasons,
            fsp_signal=signal,
        ))

    ranked.sort(key=lambda r: (-r.score, r.candidate["candidate_id"]))
    return ranked


def category_stats() -> list[dict[str, Any]]:
    categories = fixtures.all_categories()
    counts: dict[str, int] = {}
    for cand in fixtures.visible_candidates():
        code = cand.get("category_code")
        if code:
            counts[code] = counts.get(code, 0) + 1
    return [
        {
            "code": cat["code"],
            "specialization": cat["specialization"],
            "grade": cat["grade"],
            "active": cat.get("active", False),
            "candidate_count": counts.get(cat["code"], 0),
        }
        for cat in categories
    ]
