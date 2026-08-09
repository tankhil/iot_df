from datetime import UTC, datetime
from typing import Any

from sqlalchemy import desc, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import (
    PolicyDecision,
    QuarantineState,
    RecoveryObservation,
    ResponseAction,
    RiskAssessment,
    RiskLevel,
)
from app.policy.engine import PolicyContext, choose_policy
from app.response.executor import execute_actions
from app.services.audit import audit

TRUSTED_RECOVERY_SOURCE = "admin_recovery_probe"


def record_trusted_recovery_probe(
    db: Session,
    *,
    device_id: str,
    idempotency_key: str,
    actor: str = "admin",
) -> dict[str, Any]:
    settings = get_settings()
    now = datetime.now(UTC)
    quarantine = active_quarantine(db, device_id=device_id)
    if not quarantine:
        audit(
            db,
            "recovery.probe_skipped",
            device_id=device_id,
            actor=actor,
            details={"reason": "device_not_quarantined", "idempotency_key": idempotency_key},
        )
        db.commit()
        return {"created": False, "reused": False, "skipped": "device_not_quarantined", "actions": []}

    existing = db.scalar(select(RecoveryObservation).where(RecoveryObservation.idempotency_key == idempotency_key))
    if existing:
        return {
            "created": False,
            "reused": True,
            "skipped": "duplicate_probe",
            "trusted_recovery_count": trusted_recovery_count(db, quarantine=quarantine),
            "observation": _observation_dict(existing),
            "actions": [],
        }

    minimum_elapsed = (now - _as_utc(quarantine.started_at)).total_seconds() >= settings.minimum_quarantine_seconds
    completed_quarantine_action = completed_quarantine_action_for_state(db, device_id=device_id, quarantine=quarantine)
    if not completed_quarantine_action:
        audit(
            db,
            "recovery.probe_skipped",
            device_id=device_id,
            actor=actor,
            details={"reason": "missing_completed_quarantine_action", "idempotency_key": idempotency_key},
        )
        db.commit()
        return {
            "created": False,
            "reused": False,
            "skipped": "missing_completed_quarantine_action",
            "actions": [],
        }
    if not minimum_elapsed:
        audit(
            db,
            "recovery.probe_skipped",
            device_id=device_id,
            actor=actor,
            details={
                "reason": "minimum_quarantine_duration",
                "minimum_quarantine_seconds": settings.minimum_quarantine_seconds,
                "idempotency_key": idempotency_key,
            },
        )
        db.commit()
        return {"created": False, "reused": False, "skipped": "minimum_quarantine_duration", "actions": []}

    observation = RecoveryObservation(
        device_id=device_id,
        quarantine_state_id=quarantine.id,
        source=TRUSTED_RECOVERY_SOURCE,
        healthy=True,
        risk_score=0,
        details={
            "server_controlled": True,
            "minimum_quarantine_elapsed": minimum_elapsed,
            "completed_quarantine_action_id": completed_quarantine_action.id,
        },
        idempotency_key=idempotency_key,
    )
    db.add(observation)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        existing = db.scalar(select(RecoveryObservation).where(RecoveryObservation.idempotency_key == idempotency_key))
        if not existing:
            raise
        return {
            "created": False,
            "reused": True,
            "skipped": "duplicate_probe",
            "trusted_recovery_count": trusted_recovery_count(db, quarantine=quarantine),
            "observation": _observation_dict(existing),
            "actions": [],
        }

    trusted_count = trusted_recovery_count(db, quarantine=quarantine)
    assessment = RiskAssessment(
        device_id=device_id,
        detection_id=None,
        risk_score=0,
        level=RiskLevel.normal,
        reasons=[
            {
                "signal": "trusted_recovery_probe",
                "severity": "info",
                "detail": "Server-controlled recovery probe passed deterministic checks",
            }
        ],
    )
    db.add(assessment)
    db.flush()
    last_action_at = db.scalar(
        select(func.max(ResponseAction.created_at)).where(
            ResponseAction.device_id == device_id,
            ResponseAction.action.in_(["temporary_quarantine", "restore_access"]),
        )
    )
    policy = choose_policy(
        PolicyContext(
            device_id=device_id,
            risk_score=assessment.risk_score,
            consecutive_high_count=0,
            currently_quarantined=True,
            consecutive_low_count=trusted_count,
            minimum_quarantine_elapsed=minimum_elapsed,
            has_completed_quarantine_action=True,
            last_action_at=last_action_at,
            quarantine_expires_at=quarantine.expires_at,
        )
    )
    decision = PolicyDecision(
        device_id=device_id,
        risk_assessment_id=assessment.id,
        actions=policy.actions,
        rationale=policy.rationale,
    )
    db.add(decision)
    db.flush()
    observation.policy_decision_id = decision.id
    audit(
        db,
        "policy.decision",
        device_id=device_id,
        details={
            "policy_decision_id": decision.id,
            "risk_assessment_id": assessment.id,
            "actions": policy.actions,
            "rationale": policy.rationale,
            "risk": assessment.risk_score,
            "risk_level": assessment.level.value,
            "risk_reasons": assessment.reasons,
            "trusted_recovery_count": trusted_count,
        },
    )
    actions = execute_actions(db, device_id=device_id, actions=policy.actions, policy_decision=decision, actor="system")
    db.refresh(observation)
    db.refresh(assessment)
    return {
        "created": True,
        "reused": False,
        "skipped": None,
        "trusted_recovery_count": trusted_count,
        "observation": _observation_dict(observation),
        "risk": {
            "id": assessment.id,
            "risk_score": assessment.risk_score,
            "level": assessment.level.value,
            "reasons": assessment.reasons,
        },
        "policy": {
            "id": decision.id,
            "actions": decision.actions,
            "rationale": decision.rationale,
        },
        "actions": [_action_dict(action) for action in actions],
    }


def active_quarantine(db: Session, *, device_id: str) -> QuarantineState | None:
    return db.scalar(
        select(QuarantineState).where(
            QuarantineState.device_id == device_id,
            QuarantineState.active.is_(True),
        )
    )


def completed_quarantine_action_for_state(
    db: Session,
    *,
    device_id: str,
    quarantine: QuarantineState,
) -> ResponseAction | None:
    return db.scalar(
        select(ResponseAction)
        .where(
            ResponseAction.device_id == device_id,
            ResponseAction.action == "temporary_quarantine",
            ResponseAction.status == "completed",
            ResponseAction.created_at >= quarantine.started_at,
        )
        .order_by(desc(ResponseAction.created_at))
    )


def trusted_recovery_count(db: Session, *, quarantine: QuarantineState) -> int:
    last_high_at = db.scalar(
        select(func.max(RiskAssessment.created_at)).where(
            RiskAssessment.device_id == quarantine.device_id,
            RiskAssessment.level.in_([RiskLevel.high, RiskLevel.critical]),
            RiskAssessment.created_at >= quarantine.started_at,
        )
    )
    stmt = (
        select(RecoveryObservation)
        .where(
            RecoveryObservation.device_id == quarantine.device_id,
            RecoveryObservation.quarantine_state_id == quarantine.id,
            RecoveryObservation.source == TRUSTED_RECOVERY_SOURCE,
            RecoveryObservation.created_at >= quarantine.started_at,
        )
        .order_by(desc(RecoveryObservation.created_at))
        .limit(get_settings().recovery_healthy_required)
    )
    if last_high_at is not None:
        stmt = stmt.where(RecoveryObservation.created_at > last_high_at)
    rows = list(db.scalars(stmt))
    count = 0
    for row in rows:
        if row.healthy and row.risk_score < get_settings().restore_risk_threshold:
            count += 1
        else:
            break
    return count


def _observation_dict(observation: RecoveryObservation) -> dict[str, Any]:
    return {
        "id": observation.id,
        "device_id": observation.device_id,
        "quarantine_state_id": observation.quarantine_state_id,
        "policy_decision_id": observation.policy_decision_id,
        "source": observation.source,
        "healthy": observation.healthy,
        "risk_score": observation.risk_score,
        "details": observation.details,
        "idempotency_key": observation.idempotency_key,
        "created_at": observation.created_at.isoformat(),
    }


def _action_dict(action: ResponseAction) -> dict[str, Any]:
    return {
        "id": action.id,
        "device_id": action.device_id,
        "policy_decision_id": action.policy_decision_id,
        "action": action.action,
        "status": action.status,
        "result": action.result,
        "idempotency_key": action.idempotency_key,
        "created_at": action.created_at.isoformat(),
    }


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
