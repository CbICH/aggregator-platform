"""Immutable invitation snapshots and consent/contact lookup indexes."""

import sqlalchemy as sa
from alembic import op

revision = "0003_d_snapshots"
down_revision = "0002_d_profiles"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "invitations",
        sa.Column("candidate_alias", sa.String(40), nullable=False, server_default="Кандидат"),
    )
    op.add_column(
        "invitations",
        sa.Column("category_snapshot", sa.JSON(), nullable=False, server_default="{}"),
    )
    op.create_index("ix_consents_candidate_type", "consents", ["candidate_id", "consent_type"])
    op.create_index("ix_grants_company_candidate", "contact_grants", ["company_id", "candidate_id"])


def downgrade():
    op.drop_index("ix_grants_company_candidate", table_name="contact_grants")
    op.drop_index("ix_consents_candidate_type", table_name="consents")
    op.drop_column("invitations", "category_snapshot")
    op.drop_column("invitations", "candidate_alias")
