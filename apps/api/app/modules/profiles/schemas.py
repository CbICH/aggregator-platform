from typing import Annotated, Literal
from uuid import UUID

from pydantic import AwareDatetime, EmailStr, Field, field_validator, model_validator

from app.contracts.schemas import DTO, CandidatePublic, FspEvidence, VerifiedCategory

ProfileRole = Literal["backend", "frontend", "fullstack", "qa", "devops", "data", "mobile", "other"]


class ProfileContactDetails(DTO):
    email: EmailStr | None = Field(default=None, max_length=254)
    phone: str | None = Field(default=None, min_length=7, max_length=32, pattern=r"^\+?[0-9 ()-]+$")
    contact_method: str = Field(default="", max_length=200)


class ProfileContactPatch(DTO):
    email: EmailStr | None = Field(default=None, max_length=254)
    phone: str | None = Field(default=None, min_length=7, max_length=32, pattern=r"^\+?[0-9 ()-]+$")
    contact_method: str | None = Field(default=None, max_length=200)

    @field_validator("contact_method")
    @classmethod
    def non_null_method(cls, value):
        if value is None:
            raise ValueError("Use an empty string to clear contact_method")
        return value.strip()

    @field_validator("phone")
    @classmethod
    def valid_phone(cls, value):
        if value is not None and not 7 <= sum(character.isdigit() for character in value) <= 15:
            raise ValueError("Телефон должен содержать от 7 до 15 цифр")
        return value.strip() if value is not None else None


class ProfilePatch(DTO):
    expected_version: Annotated[int, Field(strict=True, ge=0)]
    full_name: str | None = Field(default=None, max_length=200)
    roles: list[ProfileRole] | None = Field(default=None, max_length=8)
    experience_months: Annotated[int | None, Field(strict=True, ge=0, le=1200)] = None
    declared_stack: list[Annotated[str, Field(min_length=1, max_length=50)]] | None = Field(
        default=None, max_length=30
    )
    soft_skills: list[Annotated[str, Field(min_length=1, max_length=80)]] | None = Field(
        default=None, max_length=20
    )
    resume_text: str | None = Field(default=None, max_length=12000)
    contacts: ProfileContactPatch | None = None
    processing_consent_accepted: Literal[True] | None = None
    processing_consent_version: str | None = Field(default=None, max_length=50)

    @field_validator("processing_consent_accepted", mode="before")
    @classmethod
    def explicit_acceptance(cls, value):
        if value is not True:
            raise ValueError("Consent acceptance must be the JSON boolean true")
        return value

    @field_validator(
        "full_name",
        "roles",
        "experience_months",
        "declared_stack",
        "soft_skills",
        "resume_text",
        "contacts",
        "processing_consent_accepted",
        "processing_consent_version",
    )
    @classmethod
    def reject_explicit_null(cls, value):
        if value is None:
            raise ValueError("Omit this field instead of sending null")
        return value

    @field_validator("full_name", "resume_text")
    @classmethod
    def trim_text(cls, value):
        return value.strip()

    @field_validator("declared_stack", "soft_skills", "roles")
    @classmethod
    def normalize_tags(cls, value, info):
        tags = [item.strip() for item in value]
        if any(not item for item in tags):
            raise ValueError("Empty list items are not allowed")
        if info.field_name == "declared_stack":
            tags = [item.lower() for item in tags]
        return list(dict.fromkeys(tags))

    @model_validator(mode="after")
    def consent_pair(self):
        if (self.processing_consent_accepted is not None) != (
            self.processing_consent_version is not None
        ):
            raise ValueError("Consent acceptance and version must be supplied together")
        return self


class ProfilePrivacy(DTO):
    publication_enabled: bool = False
    discoverable: bool = False
    visible_fields: list[str] = Field(default_factory=list)
    publication_consent_active: bool = False
    processing_consent_active: bool = False
    blocked_reasons: list[str] = Field(default_factory=list)
    version: int = 0


class CandidateSelf(DTO):
    candidate_id: UUID
    saved: bool
    version: int
    full_name: str
    alias: str
    roles: list[ProfileRole]
    experience_months: int
    declared_stack: list[str]
    soft_skills: list[str]
    resume_text: str
    contacts: ProfileContactDetails
    profile_complete: bool
    processing_consent_active: bool
    verified_category: VerifiedCategory | None = None
    fsp: FspEvidence
    privacy: ProfilePrivacy
    updated_at: AwareDatetime | None = None


class ProfileProcessingPolicy(DTO):
    version: str
    text: str


VisibleField = Literal["roles", "declared_stack", "experience_months"]


class PrivacyUpdate(DTO):
    expected_version: Annotated[int, Field(strict=True, ge=1)]
    visible_fields: list[VisibleField] | None = Field(default=None, max_length=3)
    publication_enabled: bool | None = Field(default=None, strict=True)
    publication_consent_accepted: Literal[True] | None = None
    publication_consent_version: str | None = Field(default=None, max_length=50)
    revoke_contact_access: bool = Field(default=False, strict=True)

    @field_validator("publication_consent_accepted", mode="before")
    @classmethod
    def explicit_acceptance(cls, value):
        if value is not True:
            raise ValueError("Consent acceptance must be the JSON boolean true")
        return value

    @model_validator(mode="after")
    def explicit_values(self):
        for field in self.model_fields_set:
            if getattr(self, field) is None:
                raise ValueError("Omit fields instead of sending null")
        if self.publication_enabled is True and (
            self.publication_consent_accepted is not True or not self.publication_consent_version
        ):
            raise ValueError("Publication requires explicit consent and its version")
        if self.publication_enabled is not True and (
            self.publication_consent_accepted is not None
            or self.publication_consent_version is not None
        ):
            raise ValueError("Publication consent must enable publication")
        if self.visible_fields is not None:
            self.visible_fields = list(dict.fromkeys(self.visible_fields))
        return self


class ConsentCommand(DTO):
    expected_version: Annotated[int, Field(strict=True, ge=1)]
    consent_type: Literal["publication", "contact_transfer", "profile_processing"]
    action: Literal["accept", "revoke"]
    version: str = Field(min_length=1, max_length=50)


class ConsentReceipt(DTO):
    consent_type: Literal["publication", "contact_transfer", "profile_processing"]
    version: str
    accepted_at: AwareDatetime
    revoked_at: AwareDatetime | None = None


class PrivacyResponse(ProfilePrivacy):
    consents: list[ConsentReceipt]
    publication_policy: ProfileProcessingPolicy
    contact_policy: ProfileProcessingPolicy


class PublicProfileList(DTO):
    items: list[CandidatePublic]
    next_cursor: UUID | None = None
    limit: int
