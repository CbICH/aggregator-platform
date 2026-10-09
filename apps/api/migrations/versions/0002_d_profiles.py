"""D private profiles and invitation storage"""

import sqlalchemy as sa
from alembic import op

revision = "0002_d_profiles"
down_revision = "0001_core"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "candidate_profiles",
        sa.Column("candidate_id", sa.String(length=36), nullable=False),
        sa.Column("full_name", sa.String(length=200), nullable=False),
        sa.Column("alias", sa.String(length=40), nullable=False),
        sa.Column("roles", sa.JSON(), nullable=False),
        sa.Column("experience_months", sa.Integer(), nullable=False),
        sa.Column("declared_stack", sa.JSON(), nullable=False),
        sa.Column("soft_skills", sa.JSON(), nullable=False),
        sa.Column("resume_text", sa.Text(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "experience_months >= 0 AND experience_months <= 1200", name="ck_profile_experience"
        ),
        sa.CheckConstraint("version >= 1", name="ck_profile_version"),
        sa.ForeignKeyConstraint(["candidate_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("candidate_id"),
    )
    op.create_table(
        "candidate_contacts",
        sa.Column("candidate_id", sa.String(length=36), nullable=False),
        sa.Column("email", sa.String(length=254), nullable=True),
        sa.Column("phone", sa.String(length=32), nullable=True),
        sa.Column("contact_method", sa.String(length=200), nullable=False),
        sa.ForeignKeyConstraint(
            ["candidate_id"], ["candidate_profiles.candidate_id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("candidate_id"),
    )
    op.create_table(
        "consents",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("candidate_id", sa.String(length=36), nullable=False),
        sa.Column("consent_type", sa.String(length=32), nullable=False),
        sa.Column("version", sa.String(length=50), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "consent_type IN ('profile_processing', 'publication', 'contact_transfer')",
            name="ck_consent_type",
        ),
        sa.ForeignKeyConstraint(
            ["candidate_id"], ["candidate_profiles.candidate_id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_consents_candidate_id"), "consents", ["candidate_id"], unique=False)
    op.create_table(
        "invitations",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("candidate_id", sa.String(length=36), nullable=False),
        sa.Column("company_id", sa.String(length=36), nullable=False),
        sa.Column("need_id", sa.String(length=36), nullable=True),
        sa.Column("vacancy_id", sa.String(length=36), nullable=True),
        sa.Column("company_name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("company_contact", sa.String(length=300), nullable=False),
        sa.Column("salary_min", sa.Integer(), nullable=False),
        sa.Column("salary_max", sa.Integer(), nullable=False),
        sa.Column("salary_currency", sa.String(length=3), nullable=False),
        sa.Column("salary_period", sa.String(length=10), nullable=False),
        sa.Column("salary_tax_basis", sa.String(length=10), nullable=False),
        sa.Column("evidence_snapshot", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("payload_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("viewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "salary_currency = 'RUB' AND salary_period = 'month' AND salary_tax_basis = 'gross'",
            name="ck_invitation_salary_units",
        ),
        sa.CheckConstraint(
            "status IN ('sent', 'viewed', 'accepted', 'declined')", name="ck_invitation_status"
        ),
        sa.CheckConstraint(
            "salary_min > 0 AND salary_max >= salary_min", name="ck_invitation_salary"
        ),
        sa.CheckConstraint("version >= 1", name="ck_invitation_version"),
        sa.ForeignKeyConstraint(
            ["candidate_id"], ["candidate_profiles.candidate_id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("company_id", "idempotency_key", name="uq_invitation_request"),
    )
    op.create_index(
        op.f("ix_invitations_candidate_id"), "invitations", ["candidate_id"], unique=False
    )
    op.create_index(op.f("ix_invitations_company_id"), "invitations", ["company_id"], unique=False)
    op.create_index(op.f("ix_invitations_status"), "invitations", ["status"], unique=False)
    op.create_index(
        "uq_invitation_active",
        "invitations",
        ["company_id", "candidate_id"],
        unique=True,
        postgresql_where=sa.text("status IN ('sent', 'viewed')"),
        sqlite_where=sa.text("status IN ('sent', 'viewed')"),
    )
    op.create_table(
        "visibility_settings",
        sa.Column("candidate_id", sa.String(length=36), nullable=False),
        sa.Column("publication_enabled", sa.Boolean(), nullable=False),
        sa.Column("visible_fields", sa.JSON(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["candidate_id"], ["candidate_profiles.candidate_id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("candidate_id"),
    )
    op.create_table(
        "contact_grants",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("company_id", sa.String(length=36), nullable=False),
        sa.Column("candidate_id", sa.String(length=36), nullable=False),
        sa.Column("source_kind", sa.String(length=16), nullable=False),
        sa.Column("invitation_id", sa.String(length=36), nullable=True),
        sa.Column("application_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "(source_kind = 'invitation' AND invitation_id IS NOT NULL AND application_id IS NULL) OR (source_kind = 'application' AND application_id IS NOT NULL AND invitation_id IS NULL)",
            name="ck_contact_grant_source",
        ),
        sa.ForeignKeyConstraint(
            ["candidate_id"], ["candidate_profiles.candidate_id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["invitation_id"], ["invitations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("application_id"),
        sa.UniqueConstraint("invitation_id"),
    )
    op.create_index(
        op.f("ix_contact_grants_candidate_id"), "contact_grants", ["candidate_id"], unique=False
    )
    op.create_index(
        op.f("ix_contact_grants_company_id"), "contact_grants", ["company_id"], unique=False
    )
    op.create_table(
        "invitation_events",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("invitation_id", sa.String(length=36), nullable=False),
        sa.Column("actor_id", sa.String(length=36), nullable=False),
        sa.Column("old_status", sa.String(length=16), nullable=True),
        sa.Column("new_status", sa.String(length=16), nullable=False),
        sa.Column("request_id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["actor_id"],
            ["users.id"],
        ),
        sa.ForeignKeyConstraint(["invitation_id"], ["invitations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_invitation_events_invitation_id"),
        "invitation_events",
        ["invitation_id"],
        unique=False,
    )


def downgrade():
    op.drop_index(op.f("ix_invitation_events_invitation_id"), table_name="invitation_events")
    op.drop_table("invitation_events")
    op.drop_index(op.f("ix_contact_grants_company_id"), table_name="contact_grants")
    op.drop_index(op.f("ix_contact_grants_candidate_id"), table_name="contact_grants")
    op.drop_table("contact_grants")
    op.drop_table("visibility_settings")
    op.drop_index(
        "uq_invitation_active",
        table_name="invitations",
        postgresql_where=sa.text("status IN ('sent', 'viewed')"),
        sqlite_where=sa.text("status IN ('sent', 'viewed')"),
    )
    op.drop_index(op.f("ix_invitations_status"), table_name="invitations")
    op.drop_index(op.f("ix_invitations_company_id"), table_name="invitations")
    op.drop_index(op.f("ix_invitations_candidate_id"), table_name="invitations")
    op.drop_table("invitations")
    op.drop_index(op.f("ix_consents_candidate_id"), table_name="consents")
    op.drop_table("consents")
    op.drop_table("candidate_contacts")
    op.drop_table("candidate_profiles")
