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
