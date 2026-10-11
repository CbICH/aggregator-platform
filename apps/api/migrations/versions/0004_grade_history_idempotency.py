"""Guard category history from duplicate confirmation records."""

from alembic import op

revision = "0004_grade_history_idempotency"
down_revision = "0003_assessment_survey_snapshot"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("grade_history") as batch:
        batch.create_unique_constraint(
            "uq_grade_history_candidate_assessment", ["candidate_id", "assessment_id"]
        )


def downgrade():
    with op.batch_alter_table("grade_history") as batch:
        batch.drop_constraint("uq_grade_history_candidate_assessment", type_="unique")
