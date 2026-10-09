"""Isolated real A/D API with controlled B/C ports; not the production entry point."""

import os
import subprocess
import sys
from pathlib import Path

from doubles import AssessmentDouble, CompanyDouble, FspDouble
from seed_d import seed

from app.core.config import Settings
from app.main import create_app

api_root = Path(__file__).resolve().parents[1]
database_path = api_root / "tmp/d_e2e_test.db"
database_path.parent.mkdir(exist_ok=True)
database_url = os.environ.get("D_E2E_DATABASE_URL", f"sqlite:///{database_path}")
assert database_url.endswith("_test") or database_url.endswith("_test.db")
subprocess.run(
    [sys.executable, "-m", "alembic", "upgrade", "head"],
    cwd=api_root,
    env={**os.environ, "DATABASE_URL": database_url, "PYTHONPATH": str(api_root)},
    check=True,
)
app = create_app(
    Settings(
        _env_file=None,
        app_env="test",
        database_url=database_url,
        public_app_url="http://127.0.0.1:8079",
    )
)
assessments, companies = AssessmentDouble(), CompanyDouble()
seed(app, assessments, companies)
seed(app, assessments, companies)
app.state.assessment_read_factory = lambda db: assessments
app.state.company_read_factory = lambda db: companies
app.state.fsp_read_factory = lambda db: FspDouble()
