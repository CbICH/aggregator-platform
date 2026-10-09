from io import BytesIO

from pypdf import PdfReader
from test_privacy import prepared
from test_profiles import first_profile


def test_owner_pdf_unicode_contacts_long_resume_and_no_html(d_world):
    client, _, headers = prepared(d_world)
    resume = ("Разрабатывал сервисы и проверял качество. <script>alert(1)</script>\n" * 150)[:12000]
    response = client.patch(
        "/api/v1/candidate/profile",
        json={"expected_version": 1, "resume_text": resume},
        headers=headers,
    )
    assert response.status_code == 200
    result = client.get("/api/v1/candidate/profile.pdf")
    assert result.status_code == 200 and result.headers["content-type"] == "application/pdf"
    assert result.headers["cache-control"] == "no-store"
    assert 'filename="fsp-signal-profile.pdf"' in result.headers["content-disposition"]
    assert result.content.startswith(b"%PDF") and len(result.content) > 15000
    pdf = PdfReader(BytesIO(result.content))
    text = "\n".join(page.extract_text() for page in pdf.pages)
    assert len(pdf.pages) >= 3
    for expected in [
        "Иван Петров",
        "contact@example.com",
        "+7 900 000-00-00",
        "backend:middle",
        "ФСП ID не связан",
        "Разрабатывал сервисы",
        "<script>alert(1)</script>",
    ]:
        assert expected in text
    for internal in [
        "candidate_id",
        "profile-processing-v1",
        "publication_enabled",
        "idempotency_key",
    ]:
        assert internal not in text


def test_pdf_forbidden_for_employer_unverified_anonymous_or_foreign_id(client, d_world):
    assert client.get("/api/v1/candidate/profile.pdf").status_code == 401
    owner, candidate_id, _ = prepared(d_world)
    employer, _, _ = d_world["account"]("employer@example.com", "employer")
    assert employer.get("/api/v1/candidate/profile.pdf").status_code == 403
    stranger, _, headers = d_world["account"]("stranger@example.com", verified=False)
    stranger.patch("/api/v1/candidate/profile", json=first_profile(), headers=headers)
    assert stranger.get("/api/v1/candidate/profile.pdf").status_code == 403
    assert owner.get(f"/api/v1/candidate/profiles/{candidate_id}.pdf").status_code == 404
    verified_stranger, _, _ = d_world["account"]("verified-stranger@example.com")
    assert verified_stranger.get("/api/v1/candidate/profile.pdf").status_code == 422


def test_pdf_requires_processing_consent(d_world):
    client, _, headers = prepared(d_world)
    assert (
        client.post(
            "/api/v1/candidate/consents",
            json={
                "expected_version": 1,
                "consent_type": "profile_processing",
                "action": "revoke",
                "version": "profile-processing-v1",
            },
            headers=headers,
        ).status_code
        == 200
    )
    assert client.get("/api/v1/candidate/profile.pdf").status_code == 422


def test_fsp_timeout_does_not_block_profile_or_pdf(app, d_world):
    client, _, _ = prepared(d_world)

    class UnavailableFsp:
        def get_evidence(self, candidate_id):
            raise TimeoutError("private external source")

    app.state.fsp_read_factory = lambda db: UnavailableFsp()
    profile = client.get("/api/v1/candidate/profile")
    assert profile.status_code == 200 and profile.json()["fsp"]["status"] == "unavailable"
    assert client.get("/api/v1/candidate/profile.pdf").status_code == 200
