"""add trusted recovery observations

Revision ID: 0003_trusted_recovery
Revises: 0002_model_identity_fingerprint
Create Date: 2026-08-09
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003_trusted_recovery"
down_revision: str | None = "0002_model_identity_fingerprint"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "recovery_observations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("device_id", sa.String(80), nullable=False),
        sa.Column("quarantine_state_id", sa.String(36), nullable=False),
        sa.Column("policy_decision_id", sa.String(36), nullable=True),
        sa.Column("source", sa.String(80), nullable=False),
        sa.Column("healthy", sa.Boolean(), nullable=False),
        sa.Column("risk_score", sa.Integer(), nullable=False),
        sa.Column("details", sa.JSON(), nullable=False),
        sa.Column("idempotency_key", sa.String(160), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("idempotency_key", name="uq_recovery_observations_idempotency_key"),
    )
    for column in [
        "device_id",
        "quarantine_state_id",
        "policy_decision_id",
        "source",
        "idempotency_key",
        "created_at",
    ]:
        op.create_index(f"ix_recovery_observations_{column}", "recovery_observations", [column])
    op.create_unique_constraint(
        "uq_response_actions_idempotency_key",
        "response_actions",
        ["idempotency_key"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_response_actions_idempotency_key", "response_actions", type_="unique")
    for column in [
        "created_at",
        "idempotency_key",
        "source",
        "policy_decision_id",
        "quarantine_state_id",
        "device_id",
    ]:
        op.drop_index(f"ix_recovery_observations_{column}", table_name="recovery_observations")
    op.drop_table("recovery_observations")
