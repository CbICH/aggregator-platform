"""Matching C: companies owned by employers."""

import sqlalchemy as sa
from alembic import op

revision = "0009_matching_companies"
down_revision = "0008_pilot_manual_reviews"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "companies",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "owner_user_id",
            sa.String(36),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("industry", sa.String(40), nullable=False),
        sa.Column("city", sa.String(80), nullable=False),
        sa.Column("contact_name", sa.String(120), nullable=False),
        sa.Column("contact_role", sa.String(80), nullable=True),
        sa.Column("contact_email", sa.String(254), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_companies_owner_user_id", "companies", ["owner_user_id"])


def downgrade():
    op.drop_index("ix_companies_owner_user_id", table_name="companies")
    op.drop_table("companies")
