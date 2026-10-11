"""Added owned FSP links and company search history."""

import sqlalchemy as sa
from alembic import op

revision = "0013_fsp_searches"
down_revision = "0012_merge_matching_needs"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "fsp_links",
        sa.Column(
            "candidate_id",
            sa.String(36),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("fsp_id", sa.String(100), nullable=False, unique=True),
        sa.Column("linked_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "search_snapshots",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "company_id",
            sa.String(36),
            sa.ForeignKey("companies.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("filters", sa.JSON(), nullable=False),
        sa.Column("need_snapshot", sa.JSON(), nullable=True),
        sa.Column("candidate_ids", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_search_snapshots_company_created", "search_snapshots", ["company_id", "created_at"]
    )


def downgrade():
    op.drop_index("ix_search_snapshots_company_created", table_name="search_snapshots")
    op.drop_table("search_snapshots")
    op.drop_table("fsp_links")
