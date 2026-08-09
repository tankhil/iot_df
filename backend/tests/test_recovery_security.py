from datetime import UTC, datetime, timedelta

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.session import Base
from app.models import (
    Device,
    PolicyDecision,
    QuarantineState,
    RecoveryObservation,
    ResponseAction,
    RiskAssessment,
    RiskLevel,
)
from app.response.executor import execute_actions
from app.schemas.api import TelemetryIn
from app.services.pipeline import ingest_telemetry, run_detection_cycle
from app.services.recovery import record_trusted_recovery_probe


def session() -> Session:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    return factory()


def quarantined_device(db: Session, *, started_at: datetime | None = None) -> Device:
    device = Device(
        id="camera-sec-01",
        device_type="smart_camera",
        allowed_destinations=["mqtt-broker", "health-check"],
    )
    decision = PolicyDecision(
        device_id=device.id,
        risk_assessment_id="risk-quarantine",
        actions=["temporary_quarantine"],
        rationale="test critical risk evidence",
    )
    db.add_all([device, decision])
    db.commit()
    execute_actions(db, device_id=device.id, actions=["temporary_quarantine"], policy_decision=decision)
    if started_at is not None:
        state = db.scalar(select(QuarantineState).where(QuarantineState.device_id == device.id))
        action = db.scalar(select(ResponseAction).where(ResponseAction.action == "temporary_quarantine"))
        assert state is not None
        assert action is not None
        state.started_at = started_at
        action.created_at = started_at
        db.commit()
    return device


def forged_health_check(device: Device, *, sequence: int = 1) -> TelemetryIn:
    return TelemetryIn(
        device_id=device.id,
        device_type=device.device_type,
        timestamp=datetime.now(UTC),
        topic=f"iot/{device.id}/telemetry/{sequence}",
        message_size=128,
        destination="health-check",
        auth_success=True,
        value=0.1,
    )


def count_rows(db: Session, model: object) -> int:
    return int(db.scalar(select(func.count()).select_from(model)) or 0)


def active_quarantine(db: Session, device_id: str) -> bool:
    state = db.scalar(select(QuarantineState).where(QuarantineState.device_id == device_id))
    return bool(state and state.active)


def restore_action_count(db: Session, device_id: str) -> int:
    return int(
        db.scalar(
            select(func.count()).select_from(ResponseAction).where(
                ResponseAction.device_id == device_id,
                ResponseAction.action == "restore_access",
            )
        )
        or 0
    )


def test_forged_health_check_through_public_telemetry_cannot_restore() -> None:
    db = session()
    device = quarantined_device(db, started_at=datetime.now(UTC) - timedelta(seconds=60))

    for index in range(3):
        ingest_telemetry(db, forged_health_check(device, sequence=index))
        run_detection_cycle(db, device_id=device.id)

    assert active_quarantine(db, device.id)
    assert count_rows(db, RecoveryObservation) == 0
    assert restore_action_count(db, device.id) == 0


def test_forged_mqtt_health_check_cannot_create_trusted_recovery_observation() -> None:
    db = session()
    device = quarantined_device(db, started_at=datetime.now(UTC) - timedelta(seconds=60))

    ingest_telemetry(db, forged_health_check(device))
    run_detection_cycle(db, device_id=device.id)

    assert active_quarantine(db, device.id)
    assert count_rows(db, RecoveryObservation) == 0


def test_ordinary_low_risk_telemetry_cannot_bypass_minimum_quarantine_time() -> None:
    db = session()
    device = quarantined_device(db)

    ingest_telemetry(db, forged_health_check(device))
    run_detection_cycle(db, device_id=device.id)
    trusted = record_trusted_recovery_probe(
        db,
        device_id=device.id,
        idempotency_key="camera-sec-01:min-duration",
    )

    assert trusted["skipped"] == "minimum_quarantine_duration"
    assert active_quarantine(db, device.id)
    assert restore_action_count(db, device.id) == 0


def test_untrusted_recovery_telemetry_does_not_advance_trusted_counter() -> None:
    db = session()
    device = quarantined_device(db, started_at=datetime.now(UTC) - timedelta(seconds=60))

    first = record_trusted_recovery_probe(db, device_id=device.id, idempotency_key="camera-sec-01:trusted:1")
    ingest_telemetry(db, forged_health_check(device))
    run_detection_cycle(db, device_id=device.id)
    second = record_trusted_recovery_probe(db, device_id=device.id, idempotency_key="camera-sec-01:trusted:2")

    assert first["trusted_recovery_count"] == 1
    assert second["trusted_recovery_count"] == 2
    assert count_rows(db, RecoveryObservation) == 2
    assert active_quarantine(db, device.id)


def test_post_quarantine_high_risk_resets_trusted_recovery_count() -> None:
    db = session()
    device = quarantined_device(db, started_at=datetime.now(UTC) - timedelta(seconds=60))

    first = record_trusted_recovery_probe(db, device_id=device.id, idempotency_key="camera-sec-01:reset:1")
    db.add(
        RiskAssessment(
            device_id=device.id,
            detection_id=None,
            risk_score=90,
            level=RiskLevel.critical,
            reasons=[{"signal": "test_high_evidence", "contribution": 90, "explanation": "post-quarantine evidence"}],
        )
    )
    db.commit()
    second = record_trusted_recovery_probe(db, device_id=device.id, idempotency_key="camera-sec-01:reset:2")
    third = record_trusted_recovery_probe(db, device_id=device.id, idempotency_key="camera-sec-01:reset:3")

    assert first["trusted_recovery_count"] == 1
    assert second["trusted_recovery_count"] == 1
    assert third["trusted_recovery_count"] == 2
    assert active_quarantine(db, device.id)
    assert restore_action_count(db, device.id) == 0


def test_authenticated_trusted_probes_restore_after_required_conditions() -> None:
    db = session()
    device = quarantined_device(db, started_at=datetime.now(UTC) - timedelta(seconds=60))

    results = [
        record_trusted_recovery_probe(db, device_id=device.id, idempotency_key=f"camera-sec-01:restore:{index}")
        for index in range(3)
    ]

    assert [result["trusted_recovery_count"] for result in results] == [1, 2, 3]
    assert not active_quarantine(db, device.id)
    assert restore_action_count(db, device.id) == 1
    assert results[-1]["policy"]["actions"] == ["restore_access"]


def test_replayed_trusted_probe_idempotency_key_does_not_count_twice() -> None:
    db = session()
    device = quarantined_device(db, started_at=datetime.now(UTC) - timedelta(seconds=60))

    first = record_trusted_recovery_probe(db, device_id=device.id, idempotency_key="camera-sec-01:replay:1")
    replay = record_trusted_recovery_probe(db, device_id=device.id, idempotency_key="camera-sec-01:replay:1")
    second = record_trusted_recovery_probe(db, device_id=device.id, idempotency_key="camera-sec-01:replay:2")

    assert first["created"] is True
    assert replay["reused"] is True
    assert second["trusted_recovery_count"] == 2
    assert count_rows(db, RecoveryObservation) == 2
    assert active_quarantine(db, device.id)


def test_repeated_restore_attempts_create_one_restore_action() -> None:
    db = session()
    device = quarantined_device(db, started_at=datetime.now(UTC) - timedelta(seconds=60))

    for index in range(3):
        record_trusted_recovery_probe(db, device_id=device.id, idempotency_key=f"camera-sec-01:once:{index}")
    extra = record_trusted_recovery_probe(db, device_id=device.id, idempotency_key="camera-sec-01:once:extra")

    assert extra["skipped"] == "device_not_quarantined"
    assert restore_action_count(db, device.id) == 1


def test_new_quarantine_generation_does_not_reuse_old_trusted_observations() -> None:
    db = session()
    device = quarantined_device(db, started_at=datetime.now(UTC) - timedelta(seconds=60))

    for index in range(3):
        record_trusted_recovery_probe(db, device_id=device.id, idempotency_key=f"camera-sec-01:generation-a:{index}")
    assert not active_quarantine(db, device.id)
    for observation in db.scalars(select(RecoveryObservation)).all():
        observation.created_at = datetime.now(UTC) - timedelta(seconds=120)
    db.commit()

    decision = PolicyDecision(
        device_id=device.id,
        risk_assessment_id="risk-second-quarantine",
        actions=["temporary_quarantine"],
        rationale="second simulated quarantine",
    )
    db.add(decision)
    db.commit()
    execute_actions(db, device_id=device.id, actions=["temporary_quarantine"], policy_decision=decision)
    state = db.scalar(select(QuarantineState).where(QuarantineState.device_id == device.id))
    action = db.scalar(
        select(ResponseAction)
        .where(ResponseAction.device_id == device.id, ResponseAction.action == "temporary_quarantine")
        .order_by(ResponseAction.created_at.desc())
    )
    assert state is not None
    assert action is not None
    state.started_at = datetime.now(UTC) - timedelta(seconds=60)
    action.created_at = state.started_at
    db.commit()

    first_second_generation = record_trusted_recovery_probe(
        db,
        device_id=device.id,
        idempotency_key="camera-sec-01:generation-b:1",
    )

    assert first_second_generation["trusted_recovery_count"] == 1
    assert active_quarantine(db, device.id)
