"""Matching C: employer needs."""

import sqlalchemy as sa
from alembic import op

revision = "0012_matching_needs"
down_revision = "0011_assessment_survey_index"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "employer_needs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "company_id",
            sa.String(36),
            sa.ForeignKey("companies.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("title", sa.String(160), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("specialization", sa.String(16), nullable=False),
        sa.Column("grades", sa.JSON(), nullable=False),
        sa.Column("declared_stack", sa.JSON(), nullable=False),
        sa.Column("required_skills", sa.JSON(), nullable=False),
        sa.Column("work_format", sa.String(16), nullable=False),
        sa.Column("salary_min", sa.Integer(), nullable=True),
        sa.Column("salary_max", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_employer_needs_company_id", "employer_needs", ["company_id"])


def downgrade():
    op.drop_index("ix_employer_needs_company_id", table_name="employer_needs")
    op.drop_table("employer_needs")
