from pydantic import Field, field_validator

from app.contracts.schemas import DTO, FspEvidence


class FspLinkCommand(DTO):
    fsp_id: str = Field(min_length=1, max_length=100, pattern=r"^[A-Za-z0-9_-]+$")

    @field_validator("fsp_id", mode="before")
    @classmethod
    def trim_id(cls, value):
        return value.strip() if isinstance(value, str) else value


class FspSelf(FspEvidence):
    available_fsp_id: str | None = None
    ownership_method: str = "verified_email"
