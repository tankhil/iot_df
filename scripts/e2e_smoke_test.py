import json
import os
import sys
import time
from datetime import UTC, datetime
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

API_URL = os.getenv("API_URL", "http://localhost:8000").rstrip("/")
ADMIN_API_KEY = os.getenv("ADMIN_API_KEY", "")
TIMEOUT_SECONDS = float(os.getenv("SMOKE_TIMEOUT_SECONDS", "90"))


class SmokeFailure(RuntimeError):
    pass


def request_json(
    method: str,
    path: str,
    *,
    payload: dict[str, Any] | None = None,
    admin: bool = False,
    expected: tuple[int, ...] = (200,),
) -> Any:
    headers = {"Accept": "application/json"}
    body = None
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    if admin:
        if not ADMIN_API_KEY:
            raise SmokeFailure("ADMIN_API_KEY is required for authenticated smoke stages")
        headers["X-Admin-API-Key"] = ADMIN_API_KEY
    request = Request(f"{API_URL}{path}", data=body, headers=headers, method=method)
    try:
        with urlopen(request, timeout=5) as response:
            status = response.status
            raw = response.read().decode("utf-8")
    except HTTPError as exc:
        status = exc.code
        raw = exc.read().decode("utf-8")
    except URLError as exc:
        raise SmokeFailure(f"{method} {path} failed to connect: {exc}") from exc
    if status not in expected:
        raise SmokeFailure(f"{method} {path} returned HTTP {status}: {raw[:300]}")
    return json.loads(raw) if raw else {}


def poll(stage: str, check) -> Any:  # type: ignore[no-untyped-def]
    deadline = time.monotonic() + TIMEOUT_SECONDS
    last_error = "not evaluated"
    while time.monotonic() < deadline:
        try:
            value = check()
            if value:
                return value
        except Exception as exc:  # noqa: BLE001
            last_error = str(exc)
        time.sleep(2)
    raise SmokeFailure(f"Timed out waiting for {stage}: {last_error}")


def page_count(path: str) -> int:
    value = request_json("GET", path)
    if isinstance(value, dict) and isinstance(value.get("total"), int):
        return int(value["total"])
    if isinstance(value, list):
        return len(value)
    raise SmokeFailure(f"{path} returned unexpected shape")


def post_high_risk_telemetry() -> None:
    now = datetime.now(UTC).isoformat()
    for index in range(4):
        payload = {
            "device_id": "camera-01",
            "device_type": "smart_camera",
            "timestamp": now,
            "topic": f"iot/admin/camera-01/shadow/{index}",
            "message_size": 2500,
            "destination": "unknown-simulated-destination",
            "auth_success": False,
            "value": 1.0,
        }
        request_json("POST", "/api/telemetry", payload=payload)


def main() -> int:
    evidence: dict[str, Any] = {}
    simulation_started = False
    try:
        request_json("GET", "/ready")
        evidence["api_ready"] = True

        devices = poll(
            "five simulated devices",
            lambda: request_json("GET", "/api/devices")
            if len(request_json("GET", "/api/devices")) >= 5
            else None,
        )
        evidence["device_count"] = len(devices)

        telemetry_before = page_count("/api/devices/camera-01/telemetry")
        evidence["camera_telemetry_before"] = telemetry_before

        models = request_json("GET", "/api/models")
        evidence["model_metadata_count"] = len(models)
        evidence["model_status"] = "metadata_available" if models else "safe_fallback_expected"

        start = request_json(
            "POST",
            "/api/simulations/attacks/mqtt_flood/start",
            payload={"device_id": "camera-01", "intensity": 5, "seed": 42},
            admin=True,
        )
        if start.get("status") != "started":
            raise SmokeFailure(f"safe attack did not start: {start}")
        simulation_started = True

        security_before = page_count("/api/security-events")
        detections_before = page_count("/api/detections")
        risks_before = len(request_json("GET", "/api/risks/current"))
        policies_before = page_count("/api/policy-decisions")
        actions_before = page_count("/api/response-actions")
        audit_before = page_count("/api/audit-logs")

        post_high_risk_telemetry()

        evidence["security_events_after"] = poll(
            "security event creation",
            lambda: page_count("/api/security-events")
            if page_count("/api/security-events") > security_before
            else None,
        )
        evidence["detections_after"] = poll(
            "detection creation",
            lambda: page_count("/api/detections")
            if page_count("/api/detections") > detections_before
            else None,
        )
        evidence["risk_devices_after"] = poll(
            "risk state",
            lambda: len(request_json("GET", "/api/risks/current"))
            if len(request_json("GET", "/api/risks/current")) >= risks_before
            else None,
        )
        evidence["policy_decisions_after"] = poll(
            "policy decision creation",
            lambda: page_count("/api/policy-decisions")
            if page_count("/api/policy-decisions") > policies_before
            else None,
        )
        evidence["response_actions_after"] = poll(
            "response action creation",
            lambda: page_count("/api/response-actions")
            if page_count("/api/response-actions") > actions_before
            else None,
        )
        evidence["audit_events_after"] = poll(
            "audit chain",
            lambda: page_count("/api/audit-logs") if page_count("/api/audit-logs") > audit_before else None,
        )
        evidence["quarantine_states"] = len(request_json("GET", "/api/quarantine"))

        stop = request_json(
            "POST",
            "/api/simulations/attacks/mqtt_flood/stop",
            admin=True,
        )
        simulation_started = False
        evidence["attack_stop_status"] = stop.get("status")
        print(json.dumps({"status": "passed", "evidence": evidence}, indent=2, sort_keys=True))
        return 0
    except SmokeFailure as exc:
        print(json.dumps({"status": "failed", "error": str(exc), "evidence": evidence}, indent=2), file=sys.stderr)
        return 1
    finally:
        if simulation_started:
            try:
                request_json("POST", "/api/simulations/attacks/mqtt_flood/stop", admin=True)
            except SmokeFailure as exc:
                print(f"cleanup warning: {exc}", file=sys.stderr)


if __name__ == "__main__":
    raise SystemExit(main())
