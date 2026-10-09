"""Aligned the merged B metadata with its persisted survey lookup index."""

from alembic import op

revision = "0011_assessment_survey_index"
down_revision = "0010_merge_bcd"
branch_labels = None
depends_on = None


def upgrade():
    op.create_index("ix_surveys_specialization", "surveys", ["specialization"])


def downgrade():
    op.drop_index("ix_surveys_specialization", table_name="surveys")
