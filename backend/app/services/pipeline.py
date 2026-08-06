from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from app.detection.isolation_forest import load_model, safe_fallback_detection
from app.features.extraction import EventLike, extract_features
from app.models import (
    Detection,
    Device,
    DeviceStatus,
    FeatureWindow,
    ModelVersion,
    PolicyDecision,
    QuarantineState,
    RiskAssessment,
    RiskLevel,
    SecurityEvent,
    TelemetryEvent,
)
from app.policy.engine import PolicyContext, choose_policy
from app.response.executor import execute_actions
from app.risk.engine import calculate_risk
from app.schemas.api import TelemetryIn
from app.services.audit import audit

ALLOWED_DESTINATIONS = {"mqtt-broker", "health-check"}


def upsert_device(db: Session, device_id: str, device_type: str) -> Device:
    device = db.get(Device, device_id)
    if device is None:
        device = Device(
            id=device_id,
            device_type=device_type,
            allowed_destinations=sorted(ALLOWED_DESTINATIONS),
        )
        db.add(device)
        audit(db, "device.created", device_id=device_id, details={"device_type": device_type})
    device.updated_at = datetime.now(UTC)
    return device


def ingest_telemetry(db: Session, payload: TelemetryIn) -> TelemetryEvent:
    device = upsert_device(db, payload.device_id, payload.device_type)
    quarantine = db.scalar(
        select(QuarantineState).where(
            QuarantineState.device_id == payload.device_id,
            QuarantineState.active.is_(True),
        )
    )
    processed = not quarantine or payload.destination == "health-check"
    event = TelemetryEvent(
        device_id=payload.device_id,
        device_type=payload.device_type,
        timestamp=payload.timestamp,
        topic=payload.topic,
        message_size=payload.message_size,
        destination=payload.destination,
        auth_success=payload.auth_success,
        value=payload.value,
        raw_payload=payload.model_dump(mode="json"),
        processed=processed,
    )
    db.add(event)
    if not payload.auth_success:
        db.add(
            SecurityEvent(
                device_id=payload.device_id,
                event_type="auth_failure",
                severity="medium",
                timestamp=payload.timestamp,
                details={"topic": payload.topic},
            )
        )
    if payload.destination not in ALLOWED_DESTINATIONS:
        db.add(
            SecurityEvent(
                device_id=payload.device_id,
                event_type="unknown_destination",
                severity="high",
                timestamp=payload.timestamp,
                details={"destination": payload.destination},
            )
        )
    if not payload.topic.startswith(f"iot/{payload.device_id}/"):
        db.add(
            SecurityEvent(
                device_id=payload.device_id,
                event_type="unauthorized_topic",
                severity="high",
                timestamp=payload.timestamp,
                details={"topic": payload.topic},
            )
        )
    if quarantine and not processed:
        audit(db, "telemetry.denied_by_quarantine", device_id=payload.device_id, details={"topic": payload.topic})
    if processed:
        device.status = DeviceStatus.active if device.status != DeviceStatus.quarantined else device.status
    db.commit()
    db.refresh(event)
    return event


def run_detection_cycle(db: Session, *, device_id: str, window_seconds: int = 60) -> RiskAssessment:
    now = datetime.now(UTC)
    window_start = now - timedelta(seconds=window_seconds)
    events = list(
        db.scalars(
            select(TelemetryEvent)
            .where(TelemetryEvent.device_id == device_id, TelemetryEvent.timestamp >= window_start)
            .order_by(TelemetryEvent.timestamp)
        )
    )
    if events:
        device_type = events[-1].device_type
    else:
        device = db.get(Device, device_id)
        device_type = device.device_type if device else "unknown"
    baseline = _baseline_messages_per_minute(db, device_id=device_id)
    feature_values = extract_features(
        [
            EventLike(
                timestamp=e.timestamp,
                message_size=e.message_size,
                destination=e.destination,
                auth_success=e.auth_success,
                topic=e.topic,
            )
            for e in events
        ],
        window_start,
        now,
        allowed_destinations=ALLOWED_DESTINATIONS,
        baseline_messages_per_minute=baseline,
    )
    window = FeatureWindow(
        device_id=device_id,
        device_type=device_type,
        window_start=window_start,
        window_end=now,
        features=feature_values,
    )
    db.add(window)
    db.flush()
    model_version = _active_model(db, device_type)
    detection_result = safe_fallback_detection()
    if model_version and Path(model_version.artifact_path).exists():
        detection_result = load_model(model_version.artifact_path).predict_one(feature_values)
    detection = Detection(
        device_id=device_id,
        feature_window_id=window.id,
        model_version_id=model_version.id if model_version else None,
        anomaly_score=detection_result.anomaly_score,
        is_anomaly=detection_result.is_anomaly,
        explanation=detection_result.explanation,
    )
    db.add(detection)
    db.flush()
    recent_high = _recent_high_count(db, device_id=device_id)
    risk = calculate_risk(
        device_id=device_id,
        anomaly_score=detection.anomaly_score,
        features=feature_values,
        recent_high_count=recent_high,
    )
    assessment = RiskAssessment(
        device_id=device_id,
        detection_id=detection.id,
        risk_score=risk.risk_score,
        level=risk.level,
        reasons=risk.reasons,
    )
    db.add(assessment)
    db.flush()
    quarantine = db.scalar(select(QuarantineState).where(QuarantineState.device_id == device_id, QuarantineState.active.is_(True)))
    last_action_at = db.scalar(
        select(func.max(PolicyDecision.created_at)).where(PolicyDecision.device_id == device_id)
    )
    context = PolicyContext(
        device_id=device_id,
        risk_score=assessment.risk_score,
        consecutive_high_count=recent_high + (1 if assessment.level in {RiskLevel.high, RiskLevel.critical} else 0),
        currently_quarantined=bool(quarantine),
        quarantine_expires_at=quarantine.expires_at if quarantine else None,
        last_action_at=last_action_at,
    )
    policy = choose_policy(context)
    decision = PolicyDecision(
        device_id=device_id,
        risk_assessment_id=assessment.id,
        actions=policy.actions,
        rationale=policy.rationale,
    )
    db.add(decision)
    db.flush()
    audit(db, "policy.decision", device_id=device_id, details={"actions": policy.actions, "risk": assessment.risk_score})
    execute_actions(db, device_id=device_id, actions=policy.actions, policy_decision=decision)
    db.refresh(assessment)
    return assessment


def _baseline_messages_per_minute(db: Session, *, device_id: str) -> float:
    rows = list(
        db.scalars(
            select(FeatureWindow)
            .where(FeatureWindow.device_id == device_id)
            .order_by(desc(FeatureWindow.created_at))
            .limit(10)
        )
    )
    values = [float(row.features.get("messages_per_minute", 0.0)) for row in rows]
    values = [value for value in values if value > 0]
    return sum(values) / len(values) if values else 0.0


def _recent_high_count(db: Session, *, device_id: str) -> int:
    rows = list(
        db.scalars(
            select(RiskAssessment)
            .where(RiskAssessment.device_id == device_id)
            .order_by(desc(RiskAssessment.created_at))
            .limit(3)
        )
    )
    count = 0
    for row in rows:
        if row.level in {RiskLevel.high, RiskLevel.critical}:
            count += 1
        else:
            break
    return count


def _active_model(db: Session, device_type: str) -> ModelVersion | None:
    device_type_model = db.scalar(
        select(ModelVersion)
        .where(ModelVersion.active.is_(True), ModelVersion.device_type == device_type)
        .order_by(desc(ModelVersion.created_at))
    )
    if device_type_model:
        return device_type_model
    return db.scalar(
        select(ModelVersion)
        .where(ModelVersion.active.is_(True), ModelVersion.device_type == "global")
        .order_by(desc(ModelVersion.created_at))
    )
