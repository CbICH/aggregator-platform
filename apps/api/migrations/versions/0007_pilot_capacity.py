"""Bound controlled-pilot enrollment to the planned sample size."""

import sqlalchemy as sa
from alembic import op

revision = "0007_pilot_capacity"
down_revision = "0006_controlled_pilot"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("pilot_runs") as batch:
        batch.add_column(
            sa.Column("max_participants", sa.Integer(), nullable=False, server_default="8")
        )


def downgrade():
    with op.batch_alter_table("pilot_runs") as batch:
        batch.drop_column("max_participants")
