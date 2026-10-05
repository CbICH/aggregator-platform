from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

from fastapi import Depends
from fastapi.testclient import TestClient
from sqlalchemy import func, select, update

from app.contracts.schemas import Role
from app.core.db import utcnow
from app.core.models import AuditEvent, EmailVerification, LoginSession, RegistrationConsent, User
from app.core.security import digest, require_role

PASSWORD = "correct horse battery"


def login(client, email="candidate@example.com", password=PASSWORD):
    return client.post("/api/v1/auth/login", json={"email": email, "password": password})


def verify(client, app):
    return client.post(
        "/api/v1/auth/verify-email", json={"token": app.state.mailer.messages[-1][1]}
    )


def test_registration_consent_hash_and_no_secrets(app, client, register):
    response = register()
    assert response.status_code == 202
    assert app.state.mailer.messages[0][0] == "candidate@example.com"
    token = app.state.mailer.messages[0][1]
    assert token not in response.text and PASSWORD not in response.text
    with app.state.session_factory() as db:
        user = db.scalar(select(User))
        assert user.password_hash.startswith("$argon2id$")
        assert user.password_hash != PASSWORD and not user.email_verified
        assert db.get(RegistrationConsent, user.id).version == "registration-v1"
        assert db.get(EmailVerification, digest(token)) is not None
        assert db.scalar(select(func.count()).select_from(AuditEvent)) == 1


def test_duplicate_email_does_not_replace_identity(app, client, register):
    first = register(email="Candidate@example.com")
    second = register(email="candidate@example.com", role="employer")
    assert first.json() == second.json()
    assert len(app.state.mailer.messages) == 1
    with app.state.session_factory() as db:
        assert db.scalar(select(func.count()).select_from(User)) == 1
        assert db.scalar(select(User)).role == "candidate"


def test_verification_is_single_use(app, client, register):
    register()
    assert verify(client, app).status_code == 200
    assert verify(client, app).status_code == 400
    assert login(client).json()["email_verified"] is True


def test_expired_verification_and_unknown_token(app, client, register):
    register()
    with app.state.session_factory.begin() as db:
        db.execute(update(EmailVerification).values(expires_at=utcnow() - timedelta(seconds=1)))
    assert verify(client, app).json()["error"]["code"] == "VERIFICATION_INVALID"
    assert client.post("/api/v1/auth/verify-email", json={"token": "x" * 43}).status_code == 400


def test_resend_does_not_invalidate_old_link_and_consumes_siblings(app, client, register):
    register()
    old_token = app.state.mailer.messages[0][1]
    response = client.post(
        "/api/v1/auth/resend-verification", json={"email": "candidate@example.com"}
    )
    unknown = client.post("/api/v1/auth/resend-verification", json={"email": "unknown@example.com"})
    assert response.json() == unknown.json()
    assert len(app.state.mailer.messages) == 2
    assert client.post("/api/v1/auth/verify-email", json={"token": old_token}).status_code == 200
    assert verify(client, app).status_code == 400


def test_simultaneous_verification_one_success(app, client, register):
    register()
    token = app.state.mailer.messages[0][1]

    def send(_):
        with TestClient(app) as other:
            return other.post("/api/v1/auth/verify-email", json={"token": token}).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(send, range(2))) == [200, 400]


def test_login_cookies_csrf_logout_and_replay(app, client, register):
    register()
    response = login(client)
    assert response.status_code == 200
    assert "HttpOnly" in response.headers.get_list("set-cookie")[0]
    assert "SameSite=lax" in response.headers.get_list("set-cookie")[0]
    token = client.cookies.get("signal_session")
    csrf = client.cookies.get("signal_csrf")
    with app.state.session_factory() as db:
        assert db.get(LoginSession, token) is None
        assert db.get(LoginSession, digest(token)).csrf_hash == digest(csrf)
    assert client.get("/api/v1/me").json()["role"] == "candidate"
    assert client.post("/api/v1/auth/logout").status_code == 403
    assert client.post("/api/v1/auth/logout", headers={"X-CSRF-Token": "bad"}).status_code == 403
    assert client.post("/api/v1/auth/logout", headers={"X-CSRF-Token": csrf}).status_code == 200
    client.cookies.set("signal_session", token)
    assert client.get("/api/v1/me").status_code == 401


def test_login_rotates_session(app, client, register):
    register()
    login(client)
    old = client.cookies.get("signal_session")
    login(client)
    assert old != client.cookies.get("signal_session")
    with app.state.session_factory() as db:
        assert db.get(LoginSession, digest(old)) is None


def test_session_expiry(app, client, register):
    register()
    login(client)
    with app.state.session_factory.begin() as db:
        db.execute(update(LoginSession).values(expires_at=utcnow() - timedelta(seconds=1)))
    assert client.get("/api/v1/me").json()["error"]["code"] == "SESSION_EXPIRED"


def test_wrong_password_and_unknown_user_have_same_error(client, register):
    register()
    assert (
        login(client, password="wrong password long").json()["error"]
        == login(client, email="unknown@example.com").json()["error"]
    )


def test_login_rate_limit_persists_across_requests(client):
    for _ in range(5):
        assert login(client).status_code == 401
    response = login(client)
    assert response.status_code == 429
    assert response.json()["error"]["fields"]["retry_after_seconds"] > 0


def test_origin_protection(client, register):
    register()
    response = client.post(
        "/api/v1/auth/login",
        headers={"Origin": "https://evil.example"},
        json={"email": "candidate@example.com", "password": PASSWORD},
    )
    assert response.status_code == 403
    assert not client.cookies.get("signal_session")


def test_registration_requires_current_consent_and_rejects_extra_fields(client):
    body = {
        "email": "x@example.com",
        "password": PASSWORD,
        "role": "candidate",
        "consent_accepted": False,
        "consent_version": "registration-v1",
    }
    assert client.post("/api/v1/auth/register", json=body).status_code == 422
    body["consent_accepted"] = True
    body["consent_version"] = "old"
    assert client.post("/api/v1/auth/register", json=body).status_code == 409
    body["consent_version"] = "registration-v1"
    body["email_verified"] = True
    response = client.post("/api/v1/auth/register", json=body)
    assert response.status_code == 422
    assert PASSWORD not in response.text


def test_smtp_failure_account_can_recover(app, client, register):
    app.state.mailer.fail = True
    assert register().status_code == 503
    app.state.mailer.fail = False
    assert (
        client.post(
            "/api/v1/auth/resend-verification", json={"email": "candidate@example.com"}
        ).status_code
        == 202
    )
    assert verify(client, app).status_code == 200
    assert login(client).status_code == 200


def test_role_and_email_guards(app, client, register):
    @app.get("/test/candidate")
    def candidate(actor=Depends(require_role(Role.CANDIDATE))):
        return {"id": str(actor.user_id)}

    @app.get("/test/employer")
    def employer(actor=Depends(require_role(Role.EMPLOYER))):
        return {"id": str(actor.user_id)}

    assert client.get("/test/candidate").status_code == 401
    register()
    login(client)
    assert client.get("/test/candidate").json()["error"]["code"] == "EMAIL_NOT_VERIFIED"
    verify(client, app)
    assert client.get("/test/candidate").status_code == 200
    assert client.get("/test/employer").status_code == 403


def test_employer_identity_has_no_client_controlled_company(app, client, register):
    register(email="employer@example.com", role="employer")
    verify(client, app)
    response = login(client, email="employer@example.com")
    assert response.json()["role"] == "employer"
    assert response.json()["company_id"] is None
    assert "password_hash" not in response.text
