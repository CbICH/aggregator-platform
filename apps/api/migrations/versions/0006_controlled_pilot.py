"""Controlled A/B pilot storage for assessment validation."""

import sqlalchemy as sa
from alembic import op

revision = "0006_controlled_pilot"
down_revision = "0005_assessment_integrity"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "pilot_runs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("invite_code_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("specialization", sa.String(32), nullable=False),
        sa.Column("target_grade", sa.String(16), nullable=False),
        sa.Column("catalog_version", sa.String(32), nullable=False),
        sa.Column("form_a_seed", sa.String(64), nullable=False),
        sa.Column("form_b_seed", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("closed_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_pilot_runs_status", "pilot_runs", ["status"])
    op.create_table(
        "pilot_enrollments",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "run_id",
            sa.String(36),
            sa.ForeignKey("pilot_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "candidate_id",
            sa.String(36),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("participant_code", sa.String(32), nullable=False, unique=True),
        sa.Column("form_order", sa.String(8), nullable=False),
        sa.Column("manual_grade", sa.String(16)),
        sa.Column("manual_reviewer_count", sa.Integer(), nullable=False),
        sa.Column("manual_reviewed_at", sa.DateTime(timezone=True)),
        sa.Column("joined_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("run_id", "candidate_id", name="uq_pilot_enrollment_candidate"),
    )
    op.create_index("ix_pilot_enrollments_run_id", "pilot_enrollments", ["run_id"])
    op.create_index("ix_pilot_enrollments_candidate_id", "pilot_enrollments", ["candidate_id"])
    op.create_table(
        "pilot_attempts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "enrollment_id",
            sa.String(36),
            sa.ForeignKey("pilot_enrollments.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("form_code", sa.String(1), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deadline_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("submitted_at", sa.DateTime(timezone=True)),
        sa.Column("reviewed_at", sa.DateTime(timezone=True)),
        sa.Column("score", sa.Float()),
        sa.Column("family_scores", sa.JSON()),
        sa.Column("passed", sa.Boolean()),
        sa.Column("duration_seconds", sa.Integer()),
        sa.UniqueConstraint("enrollment_id", "form_code", name="uq_pilot_attempt_form"),
        sa.UniqueConstraint("enrollment_id", "sequence", name="uq_pilot_attempt_sequence"),
    )
    for field in ("enrollment_id", "status", "deadline_at"):
        op.create_index(f"ix_pilot_attempts_{field}", "pilot_attempts", [field])
    op.create_table(
        "pilot_items",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "attempt_id",
            sa.String(36),
            sa.ForeignKey("pilot_attempts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("family", sa.String(32), nullable=False),
        sa.Column("template_id", sa.String(80), nullable=False),
        sa.Column("template_version", sa.String(32), nullable=False),
        sa.Column("private_seed", sa.String(64), nullable=False),
        sa.Column("prompt", sa.JSON(), nullable=False),
        sa.Column("rubric", sa.JSON(), nullable=False),
        sa.Column("answers", sa.JSON(), nullable=False),
        sa.Column("score", sa.Float()),
        sa.UniqueConstraint("attempt_id", "position", name="uq_pilot_item_position"),
    )
    op.create_index("ix_pilot_items_attempt_id", "pilot_items", ["attempt_id"])


def downgrade():
    for table in ("pilot_items", "pilot_attempts", "pilot_enrollments", "pilot_runs"):
        op.drop_table(table)
