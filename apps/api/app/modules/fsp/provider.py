"""Адаптер источника данных ФСП (Федерация спортивного программирования).

Назначение: абстрагировать получение сигнала ФСП (статус привязки + список
достижений) от конкретного источника. Это паттерн port/adapter из плана:

- `FspProvider` — порт (контракт, который использует matching-сервис);
- `DemoFspProvider` — текущая реализация, читает из фикстур кандидатов;
- в проде вместо DemoFspProvider подключается HttpFspProvider, который
  ходит в API ФСП. Сигнатуры совпадают — сервис подборки не меняется.

Регистрация: `app.state.fsp_provider = DemoFspProvider()` в create_app().
Демо-роутер /employer/matching/candidates берёт его через request.app.state.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Protocol

from app.modules.matching import fixtures

FspStatus = Literal["not_linked", "linked_empty", "linked_with_data", "unavailable"]


@dataclass(frozen=True)
class FspAchievement:
    """Одно подтверждённое ФСП достижение кандидата."""

    result: str
    event: str
    date: str | None = None


@dataclass(frozen=True)
class FspSignal:
    """Нормализованный сигнал ФСП по кандидату.

    `status` — состояние связки с ФСП:
      - not_linked: кандидат не привязан;
      - linked_empty: привязан, достижений нет;
      - linked_with_data: привязан, есть достижения;
      - unavailable: ФСП временно недоступен (сервис-реквест упал).
    """

    status: FspStatus
    achievements: list[FspAchievement] = field(default_factory=list)


class FspProvider(Protocol):
    """Порт: откуда модуль matching получает сведения ФСП.

    Контракт — один метод: по id кандидата вернуть FspSignal.
    Реализация решает, откуда брать (фикстуры, HTTP, кэш и т.п.).
    """

    def get_signal(self, candidate_id: str) -> FspSignal: ...


class DemoFspProvider:
    """Демо-реализация: читает ФСП из тех же фикстур кандидатов.

    Используется для хакатона и локальной разработки. В проде подменяется
    на HttpFspProvider — контракт тот же, matching-сервис не трогается.
    """

    def get_signal(self, candidate_id: str) -> FspSignal:
        for cand in fixtures.visible_candidates():
            if cand["candidate_id"] == candidate_id:
                raw = cand.get("fsp") or {}
                status: FspStatus = raw.get("status", "not_linked")
                achievements = [
                    FspAchievement(
                        result=a.get("result", ""),
                        event=a.get("event", ""),
                        date=a.get("date"),
                    )
                    for a in raw.get("achievements", [])
                ]
                return FspSignal(status=status, achievements=achievements)
        return FspSignal(status="not_linked")
