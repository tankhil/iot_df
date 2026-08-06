"""initial schema

Revision ID: 0001_initial
Revises:
Create Date: 2026-08-06
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001_initial"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    device_status = postgresql.ENUM(
        "active",
        "quarantined",
        "offline",
        name="devicestatus",
        create_type=False,
    )
    risk_level = postgresql.ENUM(
        "normal",
        "suspicious",
        "high",
        "critical",
        name="risklevel",
        create_type=False,
    )
    device_status.create(bind, checkfirst=True)
    risk_level.create(bind, checkfirst=True)
    op.create_table(
        "devices",
        sa.Column("id", sa.String(80), primary_key=True),
        sa.Column("device_type", sa.String(80), nullable=False),
        sa.Column("status", device_status, nullable=False),
        sa.Column("allowed_destinations", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table("telemetry_events", sa.Column("id", sa.String(36), primary_key=True), sa.Column("device_id", sa.String(80), nullable=False), sa.Column("device_type", sa.String(80), nullable=False), sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False), sa.Column("topic", sa.String(255), nullable=False), sa.Column("message_size", sa.Integer(), nullable=False), sa.Column("destination", sa.String(120), nullable=False), sa.Column("auth_success", sa.Boolean(), nullable=False), sa.Column("value", sa.Float(), nullable=True), sa.Column("raw_payload", sa.JSON(), nullable=False), sa.Column("processed", sa.Boolean(), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False))
    op.create_table("security_events", sa.Column("id", sa.String(36), primary_key=True), sa.Column("device_id", sa.String(80), nullable=False), sa.Column("event_type", sa.String(80), nullable=False), sa.Column("severity", sa.String(40), nullable=False), sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False), sa.Column("details", sa.JSON(), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False))
    op.create_table("feature_windows", sa.Column("id", sa.String(36), primary_key=True), sa.Column("device_id", sa.String(80), nullable=False), sa.Column("device_type", sa.String(80), nullable=False), sa.Column("window_start", sa.DateTime(timezone=True), nullable=False), sa.Column("window_end", sa.DateTime(timezone=True), nullable=False), sa.Column("features", sa.JSON(), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False))
    op.create_table("model_versions", sa.Column("id", sa.String(36), primary_key=True), sa.Column("name", sa.String(120), nullable=False), sa.Column("device_type", sa.String(80), nullable=False), sa.Column("artifact_path", sa.String(255), nullable=False), sa.Column("training_rows", sa.Integer(), nullable=False), sa.Column("metrics", sa.JSON(), nullable=False), sa.Column("active", sa.Boolean(), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False))
    op.create_table("detections", sa.Column("id", sa.String(36), primary_key=True), sa.Column("device_id", sa.String(80), nullable=False), sa.Column("feature_window_id", sa.String(36), nullable=False), sa.Column("model_version_id", sa.String(36), nullable=True), sa.Column("anomaly_score", sa.Float(), nullable=False), sa.Column("is_anomaly", sa.Boolean(), nullable=False), sa.Column("explanation", sa.JSON(), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False))
    op.create_table("risk_assessments", sa.Column("id", sa.String(36), primary_key=True), sa.Column("device_id", sa.String(80), nullable=False), sa.Column("detection_id", sa.String(36), nullable=True), sa.Column("risk_score", sa.Integer(), nullable=False), sa.Column("level", risk_level, nullable=False), sa.Column("reasons", sa.JSON(), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False))
    op.create_table("policy_decisions", sa.Column("id", sa.String(36), primary_key=True), sa.Column("device_id", sa.String(80), nullable=False), sa.Column("risk_assessment_id", sa.String(36), nullable=False), sa.Column("actions", sa.JSON(), nullable=False), sa.Column("rationale", sa.Text(), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False))
    op.create_table("response_actions", sa.Column("id", sa.String(36), primary_key=True), sa.Column("device_id", sa.String(80), nullable=False), sa.Column("policy_decision_id", sa.String(36), nullable=True), sa.Column("action", sa.String(80), nullable=False), sa.Column("status", sa.String(40), nullable=False), sa.Column("result", sa.JSON(), nullable=False), sa.Column("idempotency_key", sa.String(160), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False))
    op.create_table("quarantine_states", sa.Column("id", sa.String(36), primary_key=True), sa.Column("device_id", sa.String(80), nullable=False, unique=True), sa.Column("active", sa.Boolean(), nullable=False), sa.Column("started_at", sa.DateTime(timezone=True), nullable=False), sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False), sa.Column("max_expires_at", sa.DateTime(timezone=True), nullable=False), sa.Column("reason", sa.Text(), nullable=False), sa.Column("restored_at", sa.DateTime(timezone=True), nullable=True), sa.Column("transitions", sa.JSON(), nullable=False))
    op.create_table("audit_logs", sa.Column("id", sa.String(36), primary_key=True), sa.Column("device_id", sa.String(80), nullable=True), sa.Column("event_type", sa.String(80), nullable=False), sa.Column("actor", sa.String(80), nullable=False), sa.Column("details", sa.JSON(), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False))
    for table, cols in {
        "telemetry_events": ["device_id", "device_type", "timestamp"],
        "security_events": ["device_id", "event_type", "timestamp"],
        "feature_windows": ["device_id", "device_type", "window_start", "window_end"],
        "model_versions": ["device_type"],
        "detections": ["device_id", "feature_window_id"],
        "risk_assessments": ["device_id", "level"],
        "policy_decisions": ["device_id", "risk_assessment_id"],
        "response_actions": ["device_id", "action", "idempotency_key"],
        "quarantine_states": ["device_id", "expires_at", "max_expires_at"],
        "audit_logs": ["device_id", "event_type", "created_at"],
    }.items():
        for col in cols:
            op.create_index(f"ix_{table}_{col}", table, [col])


def downgrade() -> None:
    for table in ["audit_logs", "quarantine_states", "response_actions", "policy_decisions", "risk_assessments", "detections", "model_versions", "feature_windows", "security_events", "telemetry_events", "devices"]:
        op.drop_table(table)
    bind = op.get_bind()
    postgresql.ENUM(name="risklevel", create_type=False).drop(bind, checkfirst=True)
    postgresql.ENUM(name="devicestatus", create_type=False).drop(bind, checkfirst=True)
