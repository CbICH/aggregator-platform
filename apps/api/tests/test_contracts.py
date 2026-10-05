import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.contracts.schemas import CandidatePublic, Salary, VerifiedCategory
from app.core.config import Settings
from app.main import create_app


@pytest.mark.parametrize(
    "salary",
    [
        {"min": 0, "max": 10},
        {"min": 20, "max": 10},
        {"min": 10, "max": 20, "currency": "USD"},
        {"min": 1.5, "max": 20},
        {"min": True, "max": 20},
    ],
)
def test_salary_contract_rejects_invalid_values(salary):
    with pytest.raises(ValidationError):
        Salary.model_validate(salary)


def test_public_profile_cannot_serialize_contacts():
    with pytest.raises(ValidationError):
        CandidatePublic(
            candidate_id="10000000-0000-4000-8000-000000000001",
            display_name="Кандидат",
            declared_stack=[],
            email="private@example.com",
        )


def test_contract_fixtures():
    root = Path(__file__).resolve().parents[3]
    fixtures = json.loads((root / "fixtures/core.json").read_text())
    for row in fixtures["verified_categories"]:
        VerifiedCategory.model_validate(row)
    for row in fixtures["public_profiles"]:
        CandidatePublic.model_validate(row)


def test_openapi_and_catalog_state(client):
    schema = client.get("/api/openapi.json").json()
    assert "/api/v1/auth/register" in schema["paths"]
    assert schema["paths"]["/api/v1/me"]["get"]["security"]
    assert schema["paths"]["/api/v1/auth/login"]["post"]["responses"]["429"]
    assert all(not item["active"] for item in client.get("/api/v1/catalogs").json()["categories"])


def test_health_readiness_and_request_id(client):
    health = client.get("/api/v1/health")
    assert health.status_code == 200
    assert health.headers["x-request-id"]
    assert client.get("/api/v1/ready").status_code == 200
    assert client.get("/api/v1/me").headers["cache-control"] == "no-store"


def test_readiness_fails_without_migration(tmp_path):
    app = create_app(Settings(_env_file=None, database_url=f"sqlite:///{tmp_path / 'empty.db'}"))
    with TestClient(app) as client:
        assert client.get("/api/v1/health").status_code == 200
        assert client.get("/api/v1/ready").status_code == 503


def test_production_configuration_fails_closed():
    with pytest.raises(ValidationError):
        Settings(_env_file=None, app_env="production")
    settings = Settings(
        _env_file=None,
        app_env="production",
        public_app_url="https://signal.example",
        cookie_secure=True,
        smtp_starttls=True,
        database_url="postgresql+psycopg://user:pass@db/signal",
    )
    assert settings.cookie_secure
