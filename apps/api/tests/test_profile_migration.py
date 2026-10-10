import os
import subprocess
from pathlib import Path

import pytest
from sqlalchemy import create_engine, inspect, text


@pytest.mark.parametrize(
    "starting_revision", ["0001_core", "0003_d_snapshots", "0009_matching_companies"]
)
def test_migration_preserves_core_and_matches_models(tmp_path, starting_revision):
    api_root = Path(__file__).resolve().parents[1]
    database_url = f"sqlite:///{tmp_path / 'migration.db'}"
    env = {**os.environ, "DATABASE_URL": database_url}
    env.pop("PYTHONPATH", None)

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
    if starting_revision != "0001_core":
        alembic("upgrade", starting_revision)
    if starting_revision == "0003_d_snapshots":
        with engine.begin() as db:
            db.execute(
                text(
                    "INSERT INTO candidate_profiles (candidate_id, full_name, alias, roles, experience_months, declared_stack, soft_skills, resume_text, version, created_at, updated_at) VALUES ('10000000-0000-4000-8000-000000000001', 'Миграционный кандидат', 'Кандидат', '[]', 0, '[]', '[]', 'Сохранённое резюме', 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
                )
            )
    if starting_revision == "0009_matching_companies":
        with engine.begin() as db:
            db.execute(
                text(
                    "INSERT INTO surveys (id, candidate_id, industry, specialization, declared_grade, roles, experience_months, catalog_version, created_at) VALUES ('20000000-0000-4000-8000-000000000001', '10000000-0000-4000-8000-000000000001', 'ИТ', 'backend', 'middle', '[\"Backend developer\"]', 24, 'v1', CURRENT_TIMESTAMP)"
                )
            )
            db.execute(
                text(
                    "INSERT INTO companies (id, owner_user_id, name, description, industry, city, contact_name, contact_email, created_at, updated_at) VALUES ('30000000-0000-4000-8000-000000000001', '10000000-0000-4000-8000-000000000001', 'Сохранённая компания', 'Миграционный профиль компании', 'ИТ', 'Москва', 'Руководитель', 'hr@example.com', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
                )
            )
            db.execute(
                text(
                    "UPDATE users SET company_id = '30000000-0000-4000-8000-000000000001' WHERE id = '10000000-0000-4000-8000-000000000001'"
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
        "surveys",
        "companies",
        "verified_categories",
    }.issubset(inspect(engine).get_table_names())
    with engine.connect() as db:
        assert db.scalar(text("SELECT email FROM users")) == "migration@example.com"
        assert (
            db.scalar(text("SELECT version_num FROM alembic_version"))
            == "0012_password_resets"
        )
        if starting_revision == "0003_d_snapshots":
            assert (
                db.scalar(text("SELECT resume_text FROM candidate_profiles"))
                == "Сохранённое резюме"
            )
        if starting_revision == "0009_matching_companies":
            assert db.scalar(text("SELECT specialization FROM surveys")) == "backend"
            assert db.scalar(text("SELECT name FROM companies")) == "Сохранённая компания"
            assert (
                db.scalar(text("SELECT company_id FROM users"))
                == "30000000-0000-4000-8000-000000000001"
            )
    alembic("downgrade", "0001_core")
    assert "candidate_profiles" not in inspect(engine).get_table_names()
    with engine.connect() as db:
        assert db.scalar(text("SELECT email FROM users")) == "migration@example.com"
    engine.dispose()
