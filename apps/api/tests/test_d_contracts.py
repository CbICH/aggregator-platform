"""D contracts must remain usable by B/C without exposing private fields."""

import json
from pathlib import Path

import pytest
from pydantic import ValidationError
from test_invitations import send, setup_world

from app.contracts.schemas import FspEvidence, VerifiedCategory
from app.modules.invitations.schemas import InvitationEventResponse, InvitationResponse
from app.modules.profiles.schemas import CandidateSelf, ConsentReceipt

ROOT = Path(__file__).resolve().parents[3]


def test_d_openapi_requests_responses_and_export_are_current(client):
    schema = client.get("/api/openapi.json").json()
    exported = json.loads((ROOT / "contracts/openapi.json").read_text())
    operations = {
        "/api/v1/candidate/fsp": ["get"],
        "/api/v1/candidate/fsp-link": ["post", "delete"],
        "/api/v1/employer/matching/candidates": ["get"],
        "/api/v1/employer/searches": ["get", "post"],
        "/api/v1/employer/searches/{search_id}": ["get"],
        "/api/v1/candidate/profile": ["get", "patch"],
        "/api/v1/candidate/profile-policy": ["get"],
        "/api/v1/candidate/privacy": ["get", "patch"],
        "/api/v1/candidate/consents": ["post"],
        "/api/v1/candidate/profile.pdf": ["get"],
        "/api/v1/employer/invitation-context": ["get"],
        "/api/v1/employer/candidates": ["get"],
        "/api/v1/employer/candidates/{candidate_id}": ["get"],
        "/api/v1/employer/candidates/{candidate_id}/contacts": ["get"],
        "/api/v1/invitations": ["get", "post"],
        "/api/v1/invitations/{invitation_id}": ["get"],
        "/api/v1/invitations/{invitation_id}/events": ["get"],
        "/api/v1/invitations/{invitation_id}/view": ["post"],
        "/api/v1/invitations/{invitation_id}/decision": ["post"],
    }
    for path, methods in operations.items():
        assert schema["paths"][path] == exported["paths"][path]
        for method in methods:
            operation = schema["paths"][path][method]
            assert operation["security"]
            for status in ["400", "401", "403", "404", "409", "422"]:
                assert operation["responses"][status]["content"]["application/json"]["schema"] == {
                    "$ref": "#/components/schemas/ErrorResponse"
                }
            if method in {"patch", "post"} and not path.endswith("/view"):
                assert operation["requestBody"]["required"]
    assert (
        "application/pdf"
        in schema["paths"]["/api/v1/candidate/profile.pdf"]["get"]["responses"]["200"]["content"]
    )
    for name in ["InvitationCreate", "InvitationResponse"]:
        assert schema["components"]["schemas"][name]["properties"]["salary"] == {
            "$ref": "#/components/schemas/Salary"
        }


def test_exported_shared_and_d_dtos_forbid_undeclared_fields():
    definitions = json.loads((ROOT / "contracts/schemas.json").read_text())["$defs"]
    for name, definition in definitions.items():
        if definition.get("type") == "object":
            assert definition["additionalProperties"] is False, name
    public_fields = definitions["CandidatePublic"]["properties"]
    assert not {"email", "phone", "contacts", "full_name", "resume_text"} & public_fields.keys()


def test_d_and_fsp_timestamps_require_a_timezone(d_world):
    candidate, candidate_id, _, employer, headers = setup_world(d_world)
    invitation = send(employer, headers, candidate_id).json()
    profile = candidate.get("/api/v1/candidate/profile").json()
    privacy = candidate.get("/api/v1/candidate/privacy").json()
    event = employer.get(f"/api/v1/invitations/{invitation['invitation_id']}/events").json()[
        "items"
    ][0]
    cases = [
        (FspEvidence, {"status": "not_linked"}, ["fetched_at"]),
        (VerifiedCategory, profile["verified_category"], ["assigned_at", "next_change_at"]),
        (CandidateSelf, profile, ["updated_at"]),
        (ConsentReceipt, privacy["consents"][0], ["accepted_at", "revoked_at"]),
        (InvitationResponse, invitation, ["created_at", "viewed_at", "decided_at"]),
        (InvitationEventResponse, event, ["created_at"]),
    ]
    for model, payload, fields in cases:
        for field in fields:
            aware = {**payload, field: "2026-10-07T12:00:00+00:00"}
            if model is VerifiedCategory and field == "next_change_at":
                aware[field] = "2027-01-05T12:00:00+00:00"
            assert getattr(model.model_validate(aware), field).tzinfo is not None
            with pytest.raises(ValidationError) as error:
                model.model_validate({**aware, field: aware[field][:19]})
            assert any(item["loc"] == (field,) for item in error.value.errors())
