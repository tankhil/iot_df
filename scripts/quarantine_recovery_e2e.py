import json
import os
import sys
import time
from datetime import UTC, datetime
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

API_URL = os.getenv("API_URL", "http://localhost:8000").rstrip("/")
DEVICE_ID = os.getenv("QUARANTINE_E2E_DEVICE_ID", "camera-e2e-01")
DEVICE_TYPE = "smart_camera"
SCENARIO = "unknown_destination"
TIMEOUT_SECONDS = float(os.getenv("QUARANTINE_E2E_TIMEOUT_SECONDS", "240"))
POLL_SECONDS = float(os.getenv("QUARANTINE_E2E_POLL_SECONDS", "2"))
WINDOW_SETTLE_SECONDS = float(os.getenv("QUARANTINE_E2E_WINDOW_SETTLE_SECONDS", "65"))
START_COOLDOWN_SETTLE_SECONDS = float(os.getenv("QUARANTINE_E2E_START_COOLDOWN_SETTLE_SECONDS", "32"))
RUN_ID = str(int(time.time() * 1000))


class E2EFailure(RuntimeError):
    pass


def utcnow() -> datetime:
    return datetime.now(UTC)


def iso_now() -> str:
    return utcnow().isoformat()


def parse_time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def request_json(
    method: str,
    path: str,
    *,
    payload: dict[str, Any] | None = None,
    admin: bool = False,
    admin_header_override: str | None = None,
    expected: tuple[int, ...] = (200,),
) -> Any:
    headers = {"Accept": "application/json"}
    body = None
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    if admin:
        headers.update(admin_auth_headers(admin_header_override))
    request = Request(f"{API_URL}{path}", data=body, headers=headers, method=method)
    try:
        with urlopen(request, timeout=5) as response:
            status = response.status
            raw = response.read().decode("utf-8")
    except HTTPError as exc:
        status = exc.code
        raw = exc.read().decode("utf-8")
    except URLError as exc:
        raise E2EFailure(f"{method} {path} failed to connect: {exc}") from exc
    if status not in expected:
        raise E2EFailure(f"{method} {path} returned HTTP {status}: {raw[:300]}")
    return json.loads(raw) if raw else {}


def admin_auth_headers(override: str | None = None) -> dict[str, str]:
    value = override if override is not None else os.getenv("ADMIN_API_KEY", "")
    if not value:
        raise E2EFailure("ADMIN_API_KEY is required for authenticated quarantine E2E stages")
    return {"X-Admin-API-Key": value}


def poll_until(deadline: float, stage: str, check) -> Any:  # type: ignore[no-untyped-def]
    last = "not evaluated"
    while time.monotonic() < deadline:
        try:
            value = check()
            if value:
                return value
            last = "condition returned false"
        except Exception as exc:  # noqa: BLE001
            last = str(exc)
        remaining = max(0.0, deadline - time.monotonic())
        time.sleep(min(POLL_SECONDS, remaining))
    raise E2EFailure(f"Timed out waiting for {stage}: {last}")


def page_items(path: str, *, limit: int = 500) -> list[dict[str, Any]]:
    value = request_json("GET", f"{path}?limit={limit}&offset=0")
    if not isinstance(value, dict) or not isinstance(value.get("items"), list):
        raise E2EFailure(f"{path} returned unexpected page shape")
    return value["items"]


def records_since(path: str, since: datetime, *, device_id: str = DEVICE_ID) -> list[dict[str, Any]]:
    records = []
    for item in page_items(path):
        if item.get("device_id") != device_id:
            continue
        created_at = item.get("created_at")
        if isinstance(created_at, str) and parse_time(created_at) >= since:
            records.append(item)
    return records


def audit_since(since: datetime, *, event_type: str | None = None) -> list[dict[str, Any]]:
    rows = records_since("/api/audit-logs", since)
    if event_type:
        rows = [row for row in rows if row.get("event_type") == event_type]
    return rows


def current_device() -> dict[str, Any]:
    return request_json("GET", f"/api/devices/{DEVICE_ID}", expected=(200, 404))


def active_quarantine() -> dict[str, Any] | None:
    detail = current_device()
    quarantine = detail.get("quarantine") if isinstance(detail, dict) else None
    if isinstance(quarantine, dict) and quarantine.get("active") is True:
        return quarantine
    return None


def post_telemetry(kind: str, sequence: int) -> dict[str, Any]:
    if kind == "attack":
        payload = {
            "device_id": DEVICE_ID,
            "device_type": DEVICE_TYPE,
            "timestamp": iso_now(),
            "topic": f"iot/admin/{DEVICE_ID}/shadow/{sequence}",
            "message_size": 4096,
            "destination": "unknown-simulated-destination",
            "auth_success": False,
            "value": 1.0,
        }
    else:
        payload = {
            "device_id": DEVICE_ID,
            "device_type": DEVICE_TYPE,
            "timestamp": iso_now(),
            "topic": f"iot/{DEVICE_ID}/telemetry",
            "message_size": 128,
            "destination": "health-check",
            "auth_success": True,
            "value": 0.1,
        }
    return request_json("POST", "/api/telemetry", payload=payload)


def post_recovery_probe(sequence: int) -> dict[str, Any]:
    return request_json(
        "POST",
        f"/api/admin/devices/{DEVICE_ID}/recovery-probe",
        payload={
            "idempotency_key": f"quarantine-e2e:{DEVICE_ID}:{RUN_ID}:{sequence}",
            "reason": "bounded quarantine E2E trusted recovery observation",
        },
        admin=True,
    )


def ensure_e2e_device_purpose() -> None:
    request_json(
        "POST",
        f"/api/admin/devices/{DEVICE_ID}/purpose",
        payload={"purpose": "e2e", "device_type": DEVICE_TYPE},
        admin=True,
    )


def count_action(records: list[dict[str, Any]], action: str) -> int:
    return sum(
        1
        for row in records
        if row.get("action") == action
        and row.get("policy_decision_id")
        and row.get("status") == "completed"
    )


def policy_records_with_action(records: list[dict[str, Any]], action: str) -> list[dict[str, Any]]:
    return [row for row in records if action in (row.get("actions") or [])]


def ensure_admin_rejections() -> None:
    request_json(
        "POST",
        f"/api/admin/devices/{DEVICE_ID}/restore",
        payload={"reason": "quarantine e2e auth check"},
        expected=(401,),
    )
    request_json(
        "POST",
        f"/api/admin/devices/{DEVICE_ID}/restore",
        payload={"reason": "quarantine e2e auth check"},
        admin=True,
        admin_header_override="incorrect-admin-key",
        expected=(403,),
    )
    request_json(
        "POST",
        f"/api/admin/devices/{DEVICE_ID}/recovery-probe",
        payload={"idempotency_key": f"quarantine-e2e:{DEVICE_ID}:auth-missing", "reason": "auth check"},
        expected=(401,),
    )
    request_json(
        "POST",
        f"/api/admin/devices/{DEVICE_ID}/recovery-probe",
        payload={"idempotency_key": f"quarantine-e2e:{DEVICE_ID}:auth-wrong", "reason": "auth check"},
        admin=True,
        admin_header_override="incorrect-admin-key",
        expected=(403,),
    )


def stop_attack() -> None:
    request_json("POST", f"/api/simulations/attacks/{SCENARIO}/stop", admin=True)


def safe_restore() -> None:
    if active_quarantine():
        request_json(
            "POST",
            f"/api/admin/devices/{DEVICE_ID}/restore",
            payload={"reason": "bounded quarantine E2E cleanup"},
            admin=True,
        )


def wait_for_window_to_clear(deadline: float) -> None:
    target = time.monotonic() + WINDOW_SETTLE_SECONDS
    while time.monotonic() < min(target, deadline):
        remaining = min(target, deadline) - time.monotonic()
        time.sleep(min(POLL_SECONDS, max(0.0, remaining)))
    if time.monotonic() >= deadline:
        raise E2EFailure("Timed out while waiting for attack telemetry to age out of recovery window")


def wait_for_start_cooldown(deadline: float) -> None:
    target = time.monotonic() + START_COOLDOWN_SETTLE_SECONDS
    while time.monotonic() < min(target, deadline):
        remaining = min(target, deadline) - time.monotonic()
        time.sleep(min(POLL_SECONDS, max(0.0, remaining)))
    if time.monotonic() >= deadline:
        raise E2EFailure("Timed out while waiting for previous action cooldown before attack")


def run_sequence() -> dict[str, Any]:
    if not os.getenv("ADMIN_API_KEY", ""):
        raise E2EFailure("ADMIN_API_KEY is required for quarantine E2E")
    deadline = time.monotonic() + TIMEOUT_SECONDS
    evidence: dict[str, Any] = {
        "device_id": DEVICE_ID,
        "state_machine": [
            "normal/active",
            "suspicious/high/critical",
            "quarantine pending",
            "quarantined",
            "recovery observation",
            "restored/active",
        ],
    }
    request_json("GET", "/ready")
    ensure_admin_rejections()
    ensure_e2e_device_purpose()
    safe_restore()
    wait_for_start_cooldown(deadline)

    for index in range(2):
        post_telemetry("healthy", index)

    run_started_at = utcnow()
    start = request_json(
        "POST",
        f"/api/simulations/attacks/{SCENARIO}/start",
        payload={"device_id": DEVICE_ID, "intensity": 6, "seed": 42},
        admin=True,
    )
    if start.get("status") != "started":
        raise E2EFailure(f"safe attack did not start: {start}")

    high_risks = []
    for index in range(1, 10):
        risk = post_telemetry("attack", index)["risk"]
        high_risks.append(
            {
                "score": risk["risk_score"],
                "level": risk["level"],
                "reasons": risk["reasons"],
            }
        )
        if active_quarantine():
            break
    evidence["attack_risks"] = high_risks

    quarantine_state = poll_until(deadline, "active automatic quarantine", active_quarantine)
    evidence["quarantine_state"] = quarantine_state
    stop_attack()

    wait_for_window_to_clear(deadline)

    healthy_risks = []
    for index in range(1, 8):
        probe = post_recovery_probe(index)
        risk = probe.get("risk") or {"risk_score": 0, "level": "normal", "reasons": []}
        policy = probe.get("policy") or {}
        healthy_risks.append(
            {
                "score": risk["risk_score"],
                "level": risk["level"],
                "reasons": risk["reasons"],
                "trusted_recovery_count": probe.get("trusted_recovery_count"),
                "actions": policy.get("actions", []),
            }
        )
        if not active_quarantine():
            break
        if time.monotonic() >= deadline:
            raise E2EFailure("Timed out while submitting recovery telemetry")
        time.sleep(min(POLL_SECONDS, max(0.0, deadline - time.monotonic())))
    evidence["recovery_risks"] = healthy_risks

    final_detail = poll_until(
        deadline,
        "final active restored state",
        lambda: current_device()
        if current_device().get("device", {}).get("status") == "active" and not active_quarantine()
        else None,
    )
    evidence["final_device_status"] = final_detail["device"]["status"]
    evidence["final_quarantine_active"] = bool(active_quarantine())

    policies = records_since("/api/policy-decisions", run_started_at)
    responses = records_since("/api/response-actions", run_started_at)
    audits = audit_since(run_started_at)
    quarantine_policies = policy_records_with_action(policies, "temporary_quarantine")
    restore_policies = policy_records_with_action(policies, "restore_access")
    quarantine_actions = [row for row in responses if row.get("action") == "temporary_quarantine"]
    restore_actions = [row for row in responses if row.get("action") == "restore_access"]
    policy_audits = [row for row in audits if row.get("event_type") == "policy.decision"]
    response_audits = [
        row for row in audits if row.get("event_type") in {"response.temporary_quarantine", "response.restore_access"}
    ]

    evidence["policy_counts"] = {
        "temporary_quarantine": len(quarantine_policies),
        "restore_access": len(restore_policies),
    }
    evidence["response_counts"] = {
        "temporary_quarantine": count_action(quarantine_actions, "temporary_quarantine"),
        "restore_access": count_action(restore_actions, "restore_access"),
    }
    evidence["audit_counts"] = {
        "policy_decision": len(policy_audits),
        "response_sequence": len(response_audits),
    }
    evidence["quarantine_policy"] = quarantine_policies[0] if quarantine_policies else None
    evidence["restore_policy"] = restore_policies[0] if restore_policies else None
    evidence["response_audits"] = response_audits

    if len(quarantine_policies) != 1:
        raise E2EFailure(f"Expected exactly one automatic quarantine policy, got {len(quarantine_policies)}")
    if len(restore_policies) != 1:
        raise E2EFailure(f"Expected exactly one automatic restore policy, got {len(restore_policies)}")
    if count_action(quarantine_actions, "temporary_quarantine") != 1:
        raise E2EFailure("Expected exactly one completed automatic quarantine response")
    if count_action(restore_actions, "restore_access") != 1:
        raise E2EFailure("Expected exactly one completed automatic restore response")
    if not any(row.get("event_type") == "response.temporary_quarantine" for row in response_audits):
        raise E2EFailure("Missing correlated quarantine response audit")
    if not any(row.get("event_type") == "response.restore_access" for row in response_audits):
        raise E2EFailure("Missing correlated restore response audit")
    if max(risk["score"] for risk in high_risks) < 80:
        raise E2EFailure(f"Attack did not reach critical risk: {high_risks}")
    if len([risk for risk in healthy_risks if risk["score"] < 30]) < 3:
        raise E2EFailure(f"Recovery did not produce three low-risk windows: {healthy_risks}")
    return evidence


def main() -> int:
    started = False
    try:
        started = True
        evidence = run_sequence()
        print(json.dumps({"status": "passed", "evidence": evidence}, indent=2, sort_keys=True))
        return 0
    except E2EFailure as exc:
        try:
            if started:
                stop_attack()
                safe_restore()
        except Exception as cleanup_exc:  # noqa: BLE001
            print(f"cleanup warning: {cleanup_exc}", file=sys.stderr)
        print(json.dumps({"status": "failed", "error": str(exc)}, indent=2, sort_keys=True), file=sys.stderr)
        return 1
    finally:
        try:
            stop_attack()
        except Exception as exc:  # noqa: BLE001
            print(f"cleanup warning: {exc}", file=sys.stderr)


if __name__ == "__main__":
    raise SystemExit(main())
