"""add device purpose

Revision ID: 0004_device_purpose
Revises: 0003_trusted_recovery
Create Date: 2026-08-09
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004_device_purpose"
down_revision: str | None = "0003_trusted_recovery"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "devices",
        sa.Column("purpose", sa.String(40), nullable=False, server_default="simulated"),
    )
    op.create_index("ix_devices_purpose", "devices", ["purpose"])
    op.execute("UPDATE devices SET purpose = 'e2e' WHERE id = 'camera-e2e-01'")
    op.alter_column("devices", "purpose", server_default=None)


def downgrade() -> None:
    op.drop_index("ix_devices_purpose", table_name="devices")
    op.drop_column("devices", "purpose")
