"""Preserve independent manual-review records for the controlled pilot."""

import sqlalchemy as sa
from alembic import op

revision = "0008_pilot_manual_reviews"
down_revision = "0007_pilot_capacity"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("pilot_enrollments") as batch:
        batch.add_column(sa.Column("manual_review_resolution", sa.String(500)))
    op.create_table(
        "pilot_manual_reviews",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "enrollment_id",
            sa.String(36),
            sa.ForeignKey("pilot_enrollments.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("reviewer_code", sa.String(64), nullable=False),
        sa.Column("assessed_grade", sa.String(16), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "enrollment_id", "reviewer_code", name="uq_pilot_manual_review_reviewer"
        ),
    )
    op.create_index(
        "ix_pilot_manual_reviews_enrollment_id", "pilot_manual_reviews", ["enrollment_id"]
    )


def downgrade():
    op.drop_index("ix_pilot_manual_reviews_enrollment_id", table_name="pilot_manual_reviews")
    op.drop_table("pilot_manual_reviews")
    with op.batch_alter_table("pilot_enrollments") as batch:
        batch.drop_column("manual_review_resolution")
