"""Synthetic registry with explicit owner checks; replace this adapter for a real IdP."""

import json
from pathlib import Path
from typing import Literal, Protocol
from uuid import UUID

from pydantic import Field

from app.contracts.schemas import DTO, FspAchievementEvidence
from app.core.errors import AppError

FSP_SIGNAL_BY_RESULT = {
    "участник": 30,
    "финалист": 60,
    "призовое место": 85,
    "призёр": 85,
    "победитель": 100,
}


class FspIdentity(DTO):
    fsp_id: str
    source: Literal["demo", "registry"] = "demo"
    achievements: list[FspAchievementEvidence] = Field(default_factory=list)

    @property
    def signal(self) -> float:
        return max(
            (FSP_SIGNAL_BY_RESULT.get(a.result.lower(), 0) for a in self.achievements), default=0
        )


class FspRegistry(Protocol):
    def owned_identity(self, candidate_id: UUID, verified_email: str) -> FspIdentity: ...

    def verify_owner(self, fsp_id: str, candidate_id: UUID, verified_email: str) -> FspIdentity: ...


class DemoFspRegistry:
    """Achievements are fixed server data, never values supplied by the candidate.

    Three documented accounts have synthetic histories. Other verified accounts
    own an empty demo identity. This checks a local demo association, not ownership
    of any real participant's FSP ID.
    """

    def __init__(self, *, available: bool = True):
        self.available = available
        self.identities = json.loads(Path(__file__).with_name("demo_registry.json").read_text())[
            "identities"
        ]

    def owned_identity(self, candidate_id: UUID, verified_email: str) -> FspIdentity:
        if not self.available:
            raise AppError(503, "FSP_UNAVAILABLE", "Реестр ФСП временно недоступен")
        local, domain = verified_email.lower().split("@", 1)
        demo_email = (
            f"{local.split('+', 1)[0]}@{domain}"
            if domain == "example.com"
            else verified_email.lower()
        )
        for identity in self.identities:
            if identity["owner_email"] == demo_email:
                fsp_id = (
                    f"{identity['fsp_id']}-{candidate_id}" if "+" in local else identity["fsp_id"]
                )
                return FspIdentity(fsp_id=fsp_id, achievements=identity["achievements"])
        return FspIdentity(fsp_id=f"demo-{candidate_id}")

    def verify_owner(self, fsp_id: str, candidate_id: UUID, verified_email: str) -> FspIdentity:
        identity = self.owned_identity(candidate_id, verified_email)
        if identity.fsp_id != fsp_id:
            raise AppError(
                422, "FSP_ID_NOT_OWNED", "Не удалось подтвердить, что этот ФСП ID принадлежит вам"
            )
        return identity
