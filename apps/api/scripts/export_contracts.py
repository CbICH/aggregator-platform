"""Export stable schemas; never connects to a database or sends mail."""

import json
from pathlib import Path

from pydantic.json_schema import models_json_schema

from app.contracts.schemas import (
    ActorContext,
    CandidateContacts,
    CandidatePublic,
    CompanySummary,
    FspEvidence,
    Salary,
    VerifiedCategory,
)
from app.main import create_app
from app.modules.invitations.schemas import (
    EmployerInvitationContext,
    InvitationCreate,
    InvitationDecision,
    InvitationHistory,
    InvitationListResponse,
    InvitationResponse,
)
from app.modules.profiles.schemas import (
    CandidateSelf,
    ConsentCommand,
    ConsentReceipt,
    PrivacyResponse,
    PrivacyUpdate,
    ProfilePatch,
    ProfileProcessingPolicy,
    PublicProfileList,
)

root = Path(__file__).resolve().parents[3]
output = root / "contracts"
output.mkdir(exist_ok=True)
app = create_app()
(output / "openapi.json").write_text(
    json.dumps(app.openapi(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
)
_, schema = models_json_schema(
    [
        (m, "validation")
        for m in (
            ActorContext,
            CandidatePublic,
            CandidateContacts,
            CompanySummary,
            FspEvidence,
            Salary,
            VerifiedCategory,
            CandidateSelf,
            ProfilePatch,
            ProfileProcessingPolicy,
            PrivacyUpdate,
            PrivacyResponse,
            ConsentCommand,
            ConsentReceipt,
            PublicProfileList,
            InvitationCreate,
            InvitationDecision,
            InvitationResponse,
            InvitationListResponse,
            InvitationHistory,
            EmployerInvitationContext,
        )
    ],
    title="ФСП Сигнал: shared contracts v0.1",
)
(output / "schemas.json").write_text(json.dumps(schema, ensure_ascii=False, indent=2) + "\n")
app.state.engine.dispose()
print("Exported contracts/openapi.json and contracts/schemas.json")
