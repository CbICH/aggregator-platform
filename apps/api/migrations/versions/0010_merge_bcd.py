"""Joined existing B/C and D migration histories without rewriting applied revisions."""

revision = "0010_merge_bcd"
down_revision = ("0009_matching_companies", "0003_d_snapshots")
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass
