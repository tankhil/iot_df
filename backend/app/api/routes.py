from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from app.core.security import require_admin, sensitive_rate_limit
from app.db.session import get_db
from app.models import (
    AuditLog,
    Detection,
    Device,
    PolicyDecision,
    QuarantineState,
    ResponseAction,
    RiskAssessment,
    SecurityEvent,
    TelemetryEvent,
)
from app.response.executor import execute_actions
from app.schemas.api import (
    AttackRequest,
    AttackSimulationResponse,
    CurrentRiskResponse,
    DeviceDetailResponse,
    DeviceSummary,
    ErrorResponse,
    HealthResponse,
    ManualOverride,
    ManualOverrideResponse,
    Page,
    ReadinessResponse,
    RecoveryProbeRequest,
    RecoveryProbeResponse,
    RootResponse,
    SafeAttackScenario,
    TelemetryCreateResponse,
    TelemetryIn,
)
from app.services.pipeline import ingest_telemetry, run_detection_cycle
from app.services.recovery import record_trusted_recovery_probe

router = APIRouter()


def as_dict(obj: Any) -> dict[str, Any]:
    data = {column.name: getattr(obj, column.name) for column in obj.__table__.columns}
    for key, value in list(data.items()):
        if hasattr(value, "value"):
            data[key] = value.value
        elif hasattr(value, "isoformat"):
            data[key] = value.isoformat()
    return data


def page(db: Session, model: Any, *, limit: int, offset: int, where: Any | None = None) -> Page:
    stmt = select(model)
    count_stmt = select(func.count()).select_from(model)
    if where is not None:
        stmt = stmt.where(where)
        count_stmt = count_stmt.where(where)
    rows = db.scalars(stmt.order_by(desc(model.created_at)).limit(limit).offset(offset)).all()
    return Page(items=[as_dict(row) for row in rows], total=int(db.scalar(count_stmt) or 0), limit=limit, offset=offset)


COMMON_ERRORS: dict[int | str, dict[str, Any]] = {
    401: {"model": ErrorResponse, "description": "Admin API key is missing"},
    403: {"model": ErrorResponse, "description": "Admin API key is invalid"},
    422: {"model": ErrorResponse, "description": "Request validation failed"},
}


@router.get(
    "/",
    tags=["System"],
    summary="API root",
    description="Returns safe discovery links for the simulated defensive IoT platform.",
    response_model=RootResponse,
)
def root() -> RootResponse:
    return RootResponse()


@router.get(
    "/health",
    tags=["System"],
    summary="API liveness check",
    description="Confirms only that the FastAPI process is alive.",
    response_model=HealthResponse,
)
def health() -> HealthResponse:
    return HealthResponse(status="ok", service="api")


@router.get(
    "/ready",
    tags=["System"],
    summary="API readiness check",
    description="Checks required runtime dependencies. This endpoint does not expose internal errors.",
    response_model=ReadinessResponse,
    responses={503: {"model": ErrorResponse, "description": "A required dependency is unavailable"}},
)
def ready(db: Session = Depends(get_db)) -> ReadinessResponse:
    try:
        db.execute(select(1))
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Required dependency is unavailable",
        ) from exc
    return ReadinessResponse(status="ready", database="ok")


@router.get(
    "/api/devices",
    tags=["Devices"],
    summary="List simulated devices",
    description="Returns the current simulated IoT device inventory.",
    response_model=list[DeviceSummary],
)
def devices(db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    rows = db.scalars(select(Device).order_by(Device.id)).all()
    return [as_dict(row) for row in rows]


@router.get(
    "/api/devices/{device_id}",
    tags=["Devices"],
    summary="Get simulated device details",
    description="Returns inventory, latest risk, and quarantine state for one simulated device.",
    response_model=DeviceDetailResponse,
    responses={404: {"model": ErrorResponse, "description": "Device was not found"}},
)
def device_detail(device_id: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    device = db.get(Device, device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    risk = db.scalar(select(RiskAssessment).where(RiskAssessment.device_id == device_id).order_by(desc(RiskAssessment.created_at)))
    quarantine = db.scalar(select(QuarantineState).where(QuarantineState.device_id == device_id))
    return {
        "device": as_dict(device),
        "current_risk": as_dict(risk) if risk else None,
        "quarantine": as_dict(quarantine) if quarantine else None,
    }


@router.get(
    "/api/devices/{device_id}/telemetry",
    tags=["Telemetry"],
    summary="List device telemetry",
    description="Returns paginated telemetry events for a simulated device.",
    response_model=Page,
)
def device_telemetry(
    device_id: str,
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> Page:
    return page(db, TelemetryEvent, limit=limit, offset=offset, where=TelemetryEvent.device_id == device_id)


@router.post(
    "/api/telemetry",
    tags=["Telemetry"],
    summary="Create telemetry event",
    description="Accepts validated simulated telemetry and runs one detection/risk/policy cycle.",
    response_model=TelemetryCreateResponse,
    responses={422: {"model": ErrorResponse}},
)
def create_telemetry(payload: TelemetryIn, db: Session = Depends(get_db)) -> dict[str, Any]:
    event = ingest_telemetry(db, payload)
    risk = run_detection_cycle(db, device_id=payload.device_id)
    return {"telemetry": as_dict(event), "risk": as_dict(risk)}


@router.get(
    "/api/security-events",
    tags=["Security Events"],
    summary="List security events",
    description="Returns paginated simulated security events.",
    response_model=Page,
)
def security_events(limit: int = Query(50, ge=1, le=500), offset: int = Query(0, ge=0), db: Session = Depends(get_db)) -> Page:
    return page(db, SecurityEvent, limit=limit, offset=offset)


@router.get(
    "/api/risks/current",
    tags=["Risk Assessment"],
    summary="List current risk assessments",
    description="Returns the latest risk state for each simulated device.",
    response_model=list[CurrentRiskResponse],
)
def current_risks(db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    devices = db.scalars(select(Device)).all()
    result = []
    for device in devices:
        risk = db.scalar(select(RiskAssessment).where(RiskAssessment.device_id == device.id).order_by(desc(RiskAssessment.created_at)))
        result.append({"device_id": device.id, "device_type": device.device_type, "status": device.status.value, "risk": as_dict(risk) if risk else None})
    return result


@router.get(
    "/api/detections",
    tags=["Detection"],
    summary="List anomaly detections",
    description="Returns paginated Isolation Forest detection history.",
    response_model=Page,
)
def detections(limit: int = Query(50, ge=1, le=500), offset: int = Query(0, ge=0), db: Session = Depends(get_db)) -> Page:
    return page(db, Detection, limit=limit, offset=offset)


@router.get(
    "/api/alerts",
    tags=["Alerts"],
    summary="List alerts",
    description="Returns recent risk assessments at suspicious or higher levels.",
    response_model=list[dict[str, Any]],
)
def alerts(db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    rows = db.scalars(select(RiskAssessment).where(RiskAssessment.risk_score >= 30).order_by(desc(RiskAssessment.created_at)).limit(100)).all()
    return [as_dict(row) for row in rows]


@router.get(
    "/api/policy-decisions",
    tags=["Policy Decisions"],
    summary="List policy decisions",
    description="Returns deterministic policy decisions and selected allow-listed actions.",
    response_model=Page,
)
def policy_decisions(limit: int = Query(50, ge=1, le=500), offset: int = Query(0, ge=0), db: Session = Depends(get_db)) -> Page:
    return page(db, PolicyDecision, limit=limit, offset=offset)


@router.get(
    "/api/response-actions",
    tags=["Response Actions"],
    summary="List response actions",
    description="Returns simulated response actions. No host firewall changes are performed.",
    response_model=Page,
)
def response_actions(limit: int = Query(50, ge=1, le=500), offset: int = Query(0, ge=0), db: Session = Depends(get_db)) -> Page:
    return page(db, ResponseAction, limit=limit, offset=offset)


@router.get(
    "/api/quarantine",
    tags=["Quarantine"],
    summary="List quarantine states",
    description="Returns simulated quarantine and recovery state.",
    response_model=list[dict[str, Any]],
)
def quarantine(db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    rows = db.scalars(select(QuarantineState).order_by(desc(QuarantineState.started_at))).all()
    return [as_dict(row) for row in rows]


@router.get(
    "/api/audit-logs",
    tags=["Audit"],
    summary="List audit logs",
    description="Returns append-only application audit records for security decisions.",
    response_model=Page,
)
def audit_logs(limit: int = Query(100, ge=1, le=500), offset: int = Query(0, ge=0), db: Session = Depends(get_db)) -> Page:
    return page(db, AuditLog, limit=limit, offset=offset)


@router.get(
    "/api/models",
    tags=["ML Models"],
    summary="List model metadata",
    description="Returns saved ML model metadata. Model artifacts are not exposed.",
    response_model=list[dict[str, Any]],
)
def models(db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    from app.models import ModelVersion

    rows = db.scalars(select(ModelVersion).order_by(desc(ModelVersion.created_at))).all()
    return [as_dict(row) for row in rows]


@router.post(
    "/api/simulations/attacks/{scenario}/start",
    tags=["Simulations"],
    summary="Start safe attack simulation",
    description="Admin-only control that records the start of an allow-listed safe simulation.",
    response_model=AttackSimulationResponse,
    responses=COMMON_ERRORS,
    dependencies=[Depends(require_admin), Depends(sensitive_rate_limit)],
)
def start_attack(scenario: SafeAttackScenario, payload: AttackRequest) -> dict[str, Any]:
    from simulator.attacks.safe_attacks import start_synthetic_attack

    return start_synthetic_attack(scenario.value, payload.model_dump())


@router.post(
    "/api/simulations/attacks/{scenario}/stop",
    tags=["Simulations"],
    summary="Stop safe attack simulation",
    description="Admin-only control that records the stop of an allow-listed safe simulation.",
    response_model=AttackSimulationResponse,
    responses=COMMON_ERRORS,
    dependencies=[Depends(require_admin), Depends(sensitive_rate_limit)],
)
def stop_attack(scenario: SafeAttackScenario) -> dict[str, Any]:
    from simulator.attacks.safe_attacks import stop_synthetic_attack

    return stop_synthetic_attack(scenario.value)


@router.post(
    "/api/admin/devices/{device_id}/quarantine",
    tags=["Administration"],
    summary="Manually quarantine a simulated device",
    description="Admin-only override that applies simulated quarantine without host firewall changes.",
    response_model=ManualOverrideResponse,
    responses=COMMON_ERRORS,
    dependencies=[Depends(require_admin), Depends(sensitive_rate_limit)],
)
def manual_quarantine(
    device_id: str,
    payload: ManualOverride,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    actions = execute_actions(db, device_id=device_id, actions=["temporary_quarantine"], policy_decision=None, actor="admin")
    return {"actions": [as_dict(action) for action in actions], "reason": payload.reason}


@router.post(
    "/api/admin/devices/{device_id}/restore",
    tags=["Administration"],
    summary="Manually restore a simulated device",
    description="Admin-only override that restores simulated device access.",
    response_model=ManualOverrideResponse,
    responses=COMMON_ERRORS,
    dependencies=[Depends(require_admin), Depends(sensitive_rate_limit)],
)
def manual_restore(
    device_id: str,
    payload: ManualOverride,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    actions = execute_actions(db, device_id=device_id, actions=["restore_access"], policy_decision=None, actor="admin")
    return {"actions": [as_dict(action) for action in actions], "reason": payload.reason}


@router.post(
    "/api/admin/devices/{device_id}/recovery-probe",
    tags=["Administration"],
    summary="Submit a trusted simulated recovery probe",
    description=(
        "Admin-only control-plane probe for simulated recovery verification. "
        "Public telemetry and MQTT payloads cannot mark recovery observations trusted."
    ),
    response_model=RecoveryProbeResponse,
    responses=COMMON_ERRORS | {404: {"model": ErrorResponse, "description": "Device was not found"}},
    dependencies=[Depends(require_admin), Depends(sensitive_rate_limit)],
)
def trusted_recovery_probe(
    device_id: str,
    payload: RecoveryProbeRequest,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    if not db.get(Device, device_id):
        raise HTTPException(status_code=404, detail="Device not found")
    return record_trusted_recovery_probe(
        db,
        device_id=device_id,
        idempotency_key=payload.idempotency_key,
        actor="admin",
    )
