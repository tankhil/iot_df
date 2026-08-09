"""add model identity fingerprint

Revision ID: 0002_model_identity_fingerprint
Revises: 0001_initial
Create Date: 2026-08-09
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002_model_identity_fingerprint"
down_revision: str | None = "0001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("model_versions", sa.Column("identity_fingerprint", sa.String(64), nullable=True))
    op.add_column("model_versions", sa.Column("feature_schema_version", sa.String(40), nullable=True))
    op.add_column("model_versions", sa.Column("training_dataset_hash", sa.String(64), nullable=True))
    op.add_column("model_versions", sa.Column("hyperparameters", sa.JSON(), nullable=True))
    op.add_column("model_versions", sa.Column("training_code_version", sa.String(40), nullable=True))
    op.add_column("model_versions", sa.Column("artifact_sha256", sa.String(64), nullable=True))
    op.add_column("model_versions", sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True))

    bind = op.get_bind()
    bind.execute(
        sa.text(
            """
            UPDATE model_versions
            SET
                identity_fingerprint = 'legacy-' || id,
                feature_schema_version = 'legacy',
                training_dataset_hash = 'legacy',
                hyperparameters = CAST('{}' AS JSON),
                training_code_version = 'legacy',
                artifact_sha256 = '',
                updated_at = created_at
            WHERE identity_fingerprint IS NULL
            """
        )
    )

    for column in [
        "identity_fingerprint",
        "feature_schema_version",
        "training_dataset_hash",
        "hyperparameters",
        "training_code_version",
        "artifact_sha256",
        "updated_at",
    ]:
        op.alter_column("model_versions", column, nullable=False)

    op.create_unique_constraint(
        "uq_model_versions_identity_fingerprint",
        "model_versions",
        ["identity_fingerprint"],
    )
    op.create_index(
        "ix_model_versions_training_dataset_hash",
        "model_versions",
        ["training_dataset_hash"],
    )


def downgrade() -> None:
    op.drop_index("ix_model_versions_training_dataset_hash", table_name="model_versions")
    op.drop_constraint("uq_model_versions_identity_fingerprint", "model_versions", type_="unique")
    op.drop_column("model_versions", "updated_at")
    op.drop_column("model_versions", "artifact_sha256")
    op.drop_column("model_versions", "training_code_version")
    op.drop_column("model_versions", "hyperparameters")
    op.drop_column("model_versions", "training_dataset_hash")
    op.drop_column("model_versions", "feature_schema_version")
    op.drop_column("model_versions", "identity_fingerprint")
