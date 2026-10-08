"""Persist the survey snapshot used when an assessment starts."""

import sqlalchemy as sa
from alembic import op

revision = "0003_assessment_survey_snapshot"
down_revision = "0002_assessment"
branch_labels = None
depends_on = None


def upgrade():
    # Existing attempts are preserved; all attempts created after this migration have a snapshot.
    op.add_column("assessment_attempts", sa.Column("survey_snapshot", sa.JSON(), nullable=True))


def downgrade():
    op.drop_column("assessment_attempts", "survey_snapshot")
