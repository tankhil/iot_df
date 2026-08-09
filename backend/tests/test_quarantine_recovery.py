from datetime import UTC, datetime
from pathlib import Path

import pytest
from scripts import quarantine_recovery_e2e
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import Settings
from app.db.session import Base
from app.models import AuditLog, Device, PolicyDecision, ResponseAction
from app.response.executor import execute_actions


def test_e2e_overrides_are_rejected_outside_e2e_environment() -> None:
    with pytest.raises(ValueError, match="ENVIRONMENT=e2e"):
        Settings(_env_file=None, e2e_action_cooldown_seconds=1)


def test_e2e_overrides_apply_only_in_e2e_environment() -> None:
    settings = Settings(
        _env_file=None,
        environment="e2e",
        e2e_action_cooldown_seconds=1,
        e2e_recovery_healthy_required=2,
    )
    assert settings.action_cooldown_seconds == 1
    assert settings.recovery_healthy_required == 2


def test_response_audit_correlates_policy_decision_and_idempotency_key() -> None:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    with session_factory() as db:
        device = Device(
            id="camera-e2e-01",
            device_type="smart_camera",
            allowed_destinations=["mqtt-broker", "health-check"],
        )
        decision = PolicyDecision(
            device_id=device.id,
            risk_assessment_id="risk-1",
            actions=["temporary_quarantine"],
            rationale="test critical risk evidence",
        )
        db.add_all([device, decision])
        db.commit()

        first = execute_actions(
            db,
            device_id=device.id,
            actions=["temporary_quarantine"],
            policy_decision=decision,
        )
        second = execute_actions(
            db,
            device_id=device.id,
            actions=["temporary_quarantine"],
            policy_decision=decision,
        )
        actions = db.scalars(select(ResponseAction)).all()
        audit = db.scalar(select(AuditLog).where(AuditLog.event_type == "response.temporary_quarantine"))

    assert len(first) == 1
    assert len(second) == 1
    assert len(actions) == 1
    assert audit is not None
    assert audit.details["policy_decision_id"] == decision.id
    assert audit.details["idempotency_key"] == actions[0].idempotency_key
    assert audit.details["simulated"] is True


def test_quarantine_e2e_failure_cleanup_stops_attack_and_restores(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    calls: list[str] = []

    def fail_sequence() -> dict[str, object]:
        raise quarantine_recovery_e2e.E2EFailure("forced timeout")

    monkeypatch.setattr(quarantine_recovery_e2e, "run_sequence", fail_sequence)
    monkeypatch.setattr(quarantine_recovery_e2e, "stop_attack", lambda: calls.append("stop"))
    monkeypatch.setattr(quarantine_recovery_e2e, "safe_restore", lambda: calls.append("restore"))

    result = quarantine_recovery_e2e.main()
    captured = capsys.readouterr()

    assert result == 1
    assert calls == ["stop", "restore", "stop"]
    assert "forced timeout" in captured.err


def test_quarantine_e2e_records_since_filters_device_and_time(monkeypatch: pytest.MonkeyPatch) -> None:
    since = datetime(2026, 1, 1, tzinfo=UTC)

    def fake_page(_path: str) -> list[dict[str, object]]:
        return [
            {"device_id": "camera-e2e-01", "created_at": "2026-01-01T00:00:01+00:00"},
            {"device_id": "other", "created_at": "2026-01-01T00:00:02+00:00"},
            {"device_id": "camera-e2e-01", "created_at": "2025-12-31T23:59:59+00:00"},
        ]

    monkeypatch.setattr(quarantine_recovery_e2e, "page_items", fake_page)

    assert quarantine_recovery_e2e.records_since("/api/audit-logs", since) == [
        {"device_id": "camera-e2e-01", "created_at": "2026-01-01T00:00:01+00:00"}
    ]


def test_quarantine_e2e_script_file_does_not_print_admin_key() -> None:
    text = Path("scripts/quarantine_recovery_e2e.py").read_text(encoding="utf-8")
    assert "print(ADMIN_API_KEY" not in text
