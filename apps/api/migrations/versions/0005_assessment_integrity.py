"""Require survey snapshots and one active target per candidate."""

import sqlalchemy as sa
from alembic import op

revision = "0005_assessment_integrity"
down_revision = "0004_grade_history_idempotency"
branch_labels = None
depends_on = None


def upgrade():
    # 0003 introduced this column as nullable to preserve existing attempts. Retain those rows
    # with an explicit empty legacy snapshot, then enforce the invariant for all future writes.
    op.execute(
        "UPDATE assessment_attempts SET survey_snapshot = '{}' WHERE survey_snapshot IS NULL"
    )
    with op.batch_alter_table("assessment_attempts") as batch:
        batch.alter_column("survey_snapshot", existing_type=sa.JSON(), nullable=False)
    op.create_index(
        "uq_assessment_attempt_active_target",
        "assessment_attempts",
        ["candidate_id", "specialization", "target_grade"],
        unique=True,
        sqlite_where=sa.text("status = 'in_progress'"),
        postgresql_where=sa.text("status = 'in_progress'"),
    )


def downgrade():
    op.drop_index("uq_assessment_attempt_active_target", table_name="assessment_attempts")
    with op.batch_alter_table("assessment_attempts") as batch:
        batch.alter_column("survey_snapshot", existing_type=sa.JSON(), nullable=True)
