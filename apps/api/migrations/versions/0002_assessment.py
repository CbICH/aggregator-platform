"""Assessment B: surveys, attempts, verified categories and skill evidence."""

import sqlalchemy as sa
from alembic import op

revision = "0002_assessment"
down_revision = "0001_core"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "surveys",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "candidate_id",
            sa.String(36),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("industry", sa.String(80), nullable=False),
        sa.Column("specialization", sa.String(32), nullable=False),
        sa.Column("declared_grade", sa.String(16), nullable=False),
        sa.Column("roles", sa.JSON(), nullable=False),
        sa.Column("experience_months", sa.Integer(), nullable=False),
        sa.Column("catalog_version", sa.String(32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_surveys_candidate_id", "surveys", ["candidate_id"])
    op.create_table(
        "assessment_attempts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "candidate_id",
            sa.String(36),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "survey_id",
            sa.String(36),
            sa.ForeignKey("surveys.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("specialization", sa.String(32), nullable=False),
        sa.Column("target_grade", sa.String(16), nullable=False),
        sa.Column("catalog_version", sa.String(32), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deadline_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("submitted_at", sa.DateTime(timezone=True)),
        sa.Column("score", sa.Float()),
        sa.Column("family_scores", sa.JSON()),
        sa.Column("passed", sa.Boolean()),
        sa.Column("next_grade_recommended", sa.Boolean()),
    )
    for field in ("candidate_id", "specialization", "target_grade", "status", "deadline_at"):
        op.create_index(f"ix_assessment_attempts_{field}", "assessment_attempts", [field])
    op.create_table(
        "assessment_items",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "attempt_id",
            sa.String(36),
            sa.ForeignKey("assessment_attempts.id", ondelete="CASCADE"),
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
        sa.UniqueConstraint("attempt_id", "position", name="uq_assessment_item_position"),
    )
    op.create_index("ix_assessment_items_attempt_id", "assessment_items", ["attempt_id"])
    op.create_table(
        "verified_categories",
        sa.Column(
            "candidate_id",
            sa.String(36),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("category_code", sa.String(64), nullable=False),
        sa.Column("specialization", sa.String(32), nullable=False),
        sa.Column("verified_grade", sa.String(16), nullable=False),
        sa.Column("test_score", sa.Float(), nullable=False),
        sa.Column(
            "assessment_id",
            sa.String(36),
            sa.ForeignKey("assessment_attempts.id", ondelete="RESTRICT"),
            nullable=False,
            unique=True,
        ),
        sa.Column("assessment_version", sa.String(80), nullable=False),
        sa.Column("assigned_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("next_change_at", sa.DateTime(timezone=True), nullable=False),
    )
    for field in ("category_code", "specialization", "verified_grade", "next_change_at"):
        op.create_index(f"ix_verified_categories_{field}", "verified_categories", [field])
    op.create_table(
        "grade_history",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "candidate_id",
            sa.String(36),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "assessment_id",
            sa.String(36),
            sa.ForeignKey("assessment_attempts.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("category_code", sa.String(64), nullable=False),
        sa.Column("assigned_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("next_change_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_grade_history_candidate_id", "grade_history", ["candidate_id"])
    op.create_table(
        "skill_evidence",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "candidate_id",
            sa.String(36),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "assessment_id",
            sa.String(36),
            sa.ForeignKey("assessment_attempts.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("skill_id", sa.String(80), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("source", sa.String(24), nullable=False),
        sa.Column("assessment_version", sa.String(80), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_skill_evidence_candidate_id", "skill_evidence", ["candidate_id"])
    op.create_index("ix_skill_evidence_skill_id", "skill_evidence", ["skill_id"])


def downgrade():
    for table in (
        "skill_evidence",
        "grade_history",
        "verified_categories",
        "assessment_items",
        "assessment_attempts",
        "surveys",
    ):
        op.drop_table(table)
