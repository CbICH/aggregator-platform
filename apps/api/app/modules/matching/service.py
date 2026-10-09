"""Логика подборки кандидатов для работодателя.

Формула (из плана):
  - без потребности:   score = 0.90 * T + 0.10 * F
  - с потребностью:    score = 0.65 * T + 0.25 * R + 0.10 * F

где T — балл теста (0..100), R — взвешенное соответствие проверенных навыков
требуемым (0..100), F — сигнал ФСП (0..100, нормированный).

ВАЖНО: после слияния с ветками B и D подборка кандидатов читает реальных
опубликованных кандидатов из БД через порт `profiles` блока D (видимость =
publication_enabled && discoverable && verified_category). Фикстурные
кандидаты блока C выключены — их включение дублирует privacy-поток D.
Пока поток «реальный кандидат → подборка» не прошит в сервисе,
`rank_candidates` возвращает пустой список: эндпоинт существует, но выдача
пустая. Включение будет сделано отдельным коммитом после согласования с D.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from app.modules.fsp.provider import DemoFspProvider, FspProvider, FspSignal

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
    components: dict[str, float]
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
    """R = sum(weight_i * confirmed_score_i) / sum(weight_i), 0..100."""
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


# --- Основной API сервиса --------------------------------------------------


def rank_candidates(
    *,
    specialization: str | None = None,
    grade: Literal["junior", "middle", "senior"] | None = None,
    with_fsp_only: bool = False,
    fsp_provider: FspProvider | None = None,
) -> list[RankedCandidate]:
    """Отсортированный список опубликованных кандидатов.

    Пока источник кандидатов — профили блока D — не прошит в сервис,
    возвращает пустой список. Эндпоинт `/employer/candidates` отвечает
    `items: []`, что соответствует интеграционному сценарию B/C/D.
    Формула, веса и порт FSP (fsp_provider) сохранены для подключения
    реального источника в следующей итерации без изменения контракта.
    """
    _ = (specialization, grade, with_fsp_only, fsp_provider or _default_provider())
    return []
