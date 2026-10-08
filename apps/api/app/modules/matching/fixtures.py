"""Загрузчик демонстрационных fixtures модуля matching.

На промежуточной сдаче хакатона реальной БД seed'а ещё нет — читаем
JSON-файлы, скопированные в контейнер на этапе сборки.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve()

# Пробуем несколько путей — в контейнере и в локальной разработке
# структура разная. Используем try/except, потому что некорректный
# индекс parents[] падает с IndexError прямо на вычислении.
_PATH_ATTEMPTS: tuple[tuple[int, str], ...] = (
    (3, "fixtures-matching"),           # Docker: /app/fixtures-matching
    (5, "fixtures/matching"),           # Local dev: <repo>/fixtures/matching
)


def _resolve_root() -> Path:
    tried: list[str] = []
    for depth, suffix in _PATH_ATTEMPTS:
        try:
            candidate = _HERE.parents[depth] / suffix
        except IndexError:
            continue
        tried.append(str(candidate))
        if (candidate / "candidates.json").exists():
            return candidate
    raise FileNotFoundError(
        "Не найдена папка fixtures/matching. Попробовано: " + ", ".join(tried)
    )


@lru_cache(maxsize=1)
def _root() -> Path:
    return _resolve_root()


def _load(name: str) -> dict[str, Any]:
    path = _root() / name
    if not path.exists():
        raise FileNotFoundError(f"Fixture not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def all_candidates() -> list[dict[str, Any]]:
    return _load("candidates.json")["candidates"]


@lru_cache(maxsize=1)
def all_companies() -> list[dict[str, Any]]:
    return _load("companies.json")["companies"]


@lru_cache(maxsize=1)
def all_needs() -> list[dict[str, Any]]:
    return _load("needs.json")["needs"]


@lru_cache(maxsize=1)
def all_skills() -> list[dict[str, Any]]:
    return _load("skills.json")["skills"]


@lru_cache(maxsize=1)
def all_categories() -> list[dict[str, Any]]:
    return _load("categories.json")["categories"]


def visible_candidates() -> list[dict[str, Any]]:
    """Только кандидаты, которых можно показывать работодателю."""
    return [c for c in all_candidates() if c.get("visibility", {}).get("discoverable", False)]
