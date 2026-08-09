from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    AuditLog,
    Device,
    DeviceStatus,
    PolicyDecision,
    QuarantineState,
    ResponseAction,
)
from app.policy.engine import ALLOW_LISTED_ACTIONS, quarantine_expiry


def execute_actions(
    db: Session,
    *,
    device_id: str,
    actions: list[str],
    policy_decision: PolicyDecision | None,
    actor: str = "system",
) -> list[ResponseAction]:
    executed: list[ResponseAction] = []
    for action in actions:
        if action not in ALLOW_LISTED_ACTIONS:
            raise ValueError(f"Action is not allow-listed: {action}")
        idempotency_key = _action_idempotency_key(db, device_id=device_id, action=action, policy_decision=policy_decision)
        existing = db.scalar(select(ResponseAction).where(ResponseAction.idempotency_key == idempotency_key))
        if existing:
            executed.append(existing)
            continue
        result = _apply_action(db, device_id=device_id, action=action, actor=actor)
        response = ResponseAction(
            device_id=device_id,
            policy_decision_id=policy_decision.id if policy_decision else None,
            action=action,
            status="completed",
            result=result,
            idempotency_key=idempotency_key,
        )
        db.add(response)
        db.add(
            AuditLog(
                device_id=device_id,
                event_type=f"response.{action}",
                actor=actor,
                details={
                    **result,
                    "policy_decision_id": policy_decision.id if policy_decision else None,
                    "idempotency_key": idempotency_key,
                },
            )
        )
        executed.append(response)
    db.commit()
    return executed


def _action_idempotency_key(
    db: Session,
    *,
    device_id: str,
    action: str,
    policy_decision: PolicyDecision | None,
) -> str:
    if action == "restore_access":
        state = db.scalar(select(QuarantineState).where(QuarantineState.device_id == device_id))
        if state:
            generation = int(state.started_at.timestamp())
            return f"{device_id}:{action}:{state.id}:{generation}"
    return f"{device_id}:{action}:{policy_decision.id if policy_decision else 'manual'}"


def _apply_action(db: Session, *, device_id: str, action: str, actor: str) -> dict[str, object]:
    device = db.get(Device, device_id)
    if action == "temporary_quarantine":
        expires_at, max_expires_at = quarantine_expiry()
        state = db.scalar(select(QuarantineState).where(QuarantineState.device_id == device_id))
        now = datetime.now(UTC)
        transition = {"at": now.isoformat(), "actor": actor, "action": action}
        if state:
            state.started_at = now
            state.active = True
            state.restored_at = None
            state.expires_at = expires_at
            state.max_expires_at = max_expires_at
            state.transitions = [*state.transitions, transition]
        else:
            state = QuarantineState(
                device_id=device_id,
                active=True,
                expires_at=expires_at,
                max_expires_at=max_expires_at,
                reason="Critical repeated simulated anomaly",
                transitions=[transition],
            )
            db.add(state)
        if device:
            device.status = DeviceStatus.quarantined
        return {"simulated": True, "quarantined": True, "expires_at": expires_at.isoformat()}
    if action == "restore_access":
        state = db.scalar(select(QuarantineState).where(QuarantineState.device_id == device_id))
        if state:
            state.active = False
            state.restored_at = datetime.now(UTC)
            state.transitions = [
                *state.transitions,
                {"at": datetime.now(UTC).isoformat(), "actor": actor, "action": action},
            ]
        if device:
            device.status = DeviceStatus.active
        return {"simulated": True, "restored": True}
    return {"simulated": True, "action": action}
