"""Логика подборки кандидатов для работодателя.

На промежуточной сдаче — упрощённая версия: читаем fixtures,
считаем score по компонентам T (тест) и F (ФСП), сортируем.
Полная формула с R (релевантность потребности) будет когда появится
модуль создания потребностей (C03).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from app.modules.matching import fixtures

# Веса компонент из плана, упрощённая формула без потребности:
# score = 0.90 * T + 0.10 * F (где T и F — 0..100)
WEIGHT_TEST = 0.90
WEIGHT_FSP = 0.10

# Нормализация достижений ФСП в сигнал 0..100.
# Берём максимальный уровень достижений, не сумму.
FSP_SIGNAL_BY_RESULT: dict[str, int] = {
    "участник": 30,
    "финалист": 60,
    "призовое место": 85,
    "призёр": 85,
    "победитель": 100,
}


@dataclass
class RankedCandidate:
    """Одна строка в выдаче — всё что нужно для карточки на фронте."""

    candidate: dict[str, Any]
    score: float
    components: dict[str, float]  # {"test": 86, "fsp": 60}
    reasons: list[dict[str, Any]]  # ["GRADE_VERIFIED", "FSP_SIGNAL", "SKILL_MATCH:api.sql"]


def fsp_signal(candidate: dict[str, Any]) -> float:
    """Переводит достижения ФСП кандидата в сигнал 0..100.

    Нет связи или нет достижений → 0.
    Статус unavailable → 0, но причина отдельная (пометка на фронте).
    """
    fsp = candidate.get("fsp", {})
    status = fsp.get("status", "not_linked")
    if status != "linked_with_data":
        return 0.0
    best = 0
    for achievement in fsp.get("achievements", []):
        result = (achievement.get("result") or "").lower()
        value = FSP_SIGNAL_BY_RESULT.get(result, 0)
        if value > best:
            best = value
    return float(best)


def compute_reasons(candidate: dict[str, Any]) -> list[dict[str, Any]]:
    """Короткие причины «почему подходит», в порядке важности для показа."""
    reasons: list[dict[str, Any]] = []
    verified_grade = candidate.get("verified_grade")
    if verified_grade:
        reasons.append(
            {
                "code": "GRADE_VERIFIED",
                "label": f"{verified_grade.title()} подтверждён тестом",
            }
        )
    for skill in candidate.get("skills", []):
        reasons.append(
            {
                "code": "SKILL",
                "skill_id": skill["id"],
                "score": skill["score"],
            }
        )
    fsp = candidate.get("fsp", {})
    if fsp.get("status") == "linked_with_data":
        achievements = fsp.get("achievements", [])
        if achievements:
            top = max(
                achievements,
                key=lambda a: FSP_SIGNAL_BY_RESULT.get((a.get("result") or "").lower(), 0),
            )
            reasons.append(
                {
                    "code": "FSP_SIGNAL",
                    "label": f"{top.get('result', '').capitalize()}: {top.get('event', '')}",
                    "date": top.get("date"),
                }
            )
    elif fsp.get("status") == "unavailable":
        reasons.append(
            {
                "code": "FSP_UNAVAILABLE",
                "label": "Статус ФСП временно недоступен",
            }
        )
    return reasons


def rank_candidates(
    *,
    specialization: str | None = None,
    grade: Literal["junior", "middle", "senior"] | None = None,
    with_fsp_only: bool = False,
) -> list[RankedCandidate]:
    """Возвращает отсортированный список кандидатов для работодателя."""
    pool = fixtures.visible_candidates()
    if specialization:
        pool = [c for c in pool if c.get("specialization") == specialization]
    if grade:
        pool = [c for c in pool if c.get("verified_grade") == grade]
    if with_fsp_only:
        pool = [c for c in pool if c.get("fsp", {}).get("status") == "linked_with_data"]

    ranked: list[RankedCandidate] = []
    for candidate in pool:
        test_score = float(candidate.get("assessment", {}).get("test_score", 0))
        fsp = fsp_signal(candidate)
        score = round(WEIGHT_TEST * test_score + WEIGHT_FSP * fsp, 1)
        ranked.append(
            RankedCandidate(
                candidate=candidate,
                score=score,
                components={"test": test_score, "fsp": fsp},
                reasons=compute_reasons(candidate),
            )
        )
    # Устойчивая сортировка: по score убывание, при равенстве — по id для стабильности
    ranked.sort(key=lambda r: (-r.score, r.candidate["candidate_id"]))
    return ranked


def category_stats() -> list[dict[str, Any]]:
    """Сколько кандидатов доступно в каждой из активных категорий."""
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
