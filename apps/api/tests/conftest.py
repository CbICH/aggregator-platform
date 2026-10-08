import os
from dataclasses import dataclass, field

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.engine import make_url

from app.core.config import Settings
from app.core.db import Base
from app.main import create_app


@dataclass
class Mailbox:
    messages: list[tuple[str, str]] = field(default_factory=list)
    fail: bool = False

    def send_verification(self, email: str, token: str):
        if self.fail:
            raise OSError("SMTP offline")
        self.messages.append((email, token))


@pytest.fixture
def app(tmp_path):
    database_url = os.environ.get("TEST_DATABASE_URL", f"sqlite:///{tmp_path / 'test.db'}")
    if database_url.startswith("postgresql"):
        # Never reset a developer's non-test database through a misconfigured env var.
        assert (make_url(database_url).database or "").endswith("_test")
    application = create_app(
        Settings(_env_file=None, app_env="test", database_url=database_url), mailer=Mailbox()
    )
    Base.metadata.create_all(application.state.engine)
    yield application
    Base.metadata.drop_all(application.state.engine)
    application.state.engine.dispose()


@pytest.fixture
def client(app):
    with TestClient(app) as value:
        yield value


@pytest.fixture
def register(client):
    def create(email="candidate@example.com", role="candidate"):
        return client.post(
            "/api/v1/auth/register",
            json={
                "email": email,
                "password": "correct horse battery",
                "role": role,
                "consent_accepted": True,
                "consent_version": "registration-v1",
            },
        )

    return create


@pytest.fixture
def d_world(app):
    from doubles import AssessmentDouble, CompanyDouble, FspDouble
    from fastapi.testclient import TestClient
    from sqlalchemy import update

    from app.core.models import User

    assessments, companies = AssessmentDouble(), CompanyDouble()
    app.state.assessment_read_factory = lambda db: assessments
    app.state.company_read_factory = lambda db: companies
    app.state.fsp_read_factory = lambda db: FspDouble()
    clients = []

    def account(email, role="candidate", verified=True, company_id=None):
        client = TestClient(app)
        clients.append(client)
        response = client.post(
            "/api/v1/auth/register",
            json={
                "email": email,
                "role": role,
                "password": "correct horse battery",
                "consent_accepted": True,
                "consent_version": "registration-v1",
            },
        )
        assert response.status_code == 202, response.text
        if verified:
            token = next(
                token for address, token in reversed(app.state.mailer.messages) if address == email
            )
            assert (
                client.post("/api/v1/auth/verify-email", json={"token": token}).status_code == 200
            )
        actor = client.post(
            "/api/v1/auth/login", json={"email": email, "password": "correct horse battery"}
        ).json()
        if company_id:
            with app.state.session_factory.begin() as db:
                db.execute(update(User).where(User.id == actor["id"]).values(company_id=company_id))
            companies.add(company_id, "Компания " + email.split("@")[0])
        return client, actor["id"], {"X-CSRF-Token": client.cookies.get("signal_csrf")}

    yield {"account": account, "assessments": assessments, "companies": companies}
    for client in clients:
        client.close()
