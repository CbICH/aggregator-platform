import os
import subprocess
from pathlib import Path

from sqlalchemy import create_engine, inspect, text


def test_migration_preserves_core_and_matches_models(tmp_path):
    api_root = Path(__file__).resolve().parents[1]
    database_url = f"sqlite:///{tmp_path / 'migration.db'}"
    env = {**os.environ, "DATABASE_URL": database_url, "PYTHONPATH": str(api_root)}

    def alembic(*args):
        result = subprocess.run(
            [os.sys.executable, "-m", "alembic", *args],
            cwd=api_root,
            env=env,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, result.stdout + result.stderr

    alembic("upgrade", "0001_core")
    engine = create_engine(database_url)
    with engine.begin() as db:
        db.execute(
            text(
                "INSERT INTO users (id, email, password_hash, role, email_verified, created_at) VALUES ('10000000-0000-4000-8000-000000000001', 'migration@example.com', 'test-hash', 'candidate', 0, CURRENT_TIMESTAMP)"
            )
        )
    alembic("upgrade", "head")
    alembic("check")
    assert {
        "candidate_profiles",
        "candidate_contacts",
        "visibility_settings",
        "consents",
        "invitations",
        "invitation_events",
        "contact_grants",
    }.issubset(inspect(engine).get_table_names())
    with engine.connect() as db:
        assert db.scalar(text("SELECT email FROM users")) == "migration@example.com"
    alembic("downgrade", "0001_core")
    assert "candidate_profiles" not in inspect(engine).get_table_names()
    with engine.connect() as db:
        assert db.scalar(text("SELECT email FROM users")) == "migration@example.com"
    engine.dispose()
