import argparse
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
API_URL = os.getenv("API_URL", "http://localhost:8000").rstrip("/")
DASHBOARD_URL = os.getenv("DASHBOARD_URL", "http://localhost:5173").rstrip("/")
TIMEOUT_SECONDS = int(os.getenv("FOUNDATION_VERIFY_TIMEOUT_SECONDS", "120"))
SERVICES = ("postgres", "mosquitto", "migrate", "api", "collector", "simulator", "dashboard")
API_COLLECTIONS = {
    "security_events": "/api/security-events",
    "detections": "/api/detections",
    "policy_decisions": "/api/policy-decisions",
    "response_actions": "/api/response-actions",
    "audit_logs": "/api/audit-logs",
}


class VerificationFailure(RuntimeError):
    pass


def load_admin_key() -> str:
    env_path = ROOT / ".env"
    if not env_path.exists():
        return ""
    for line in env_path.read_text(encoding="utf-8").splitlines():
        if line.startswith("ADMIN_API_KEY="):
            return line.split("=", 1)[1].strip()
    return ""


ADMIN_API_KEY = load_admin_key()


def redact(text: str) -> str:
    if ADMIN_API_KEY:
        text = text.replace(ADMIN_API_KEY, "<redacted-admin-api-key>")
    return re.sub(r"(X-Admin-API-Key:\s*)\\S+", r"\\1<redacted>", text, flags=re.IGNORECASE)


def run_command(label: str, args: list[str], *, timeout: int = 600, required: bool = True) -> subprocess.CompletedProcess[str]:
    print(f"\n## {label}")
    print("+ " + " ".join(args))
    result = subprocess.run(args, cwd=ROOT, text=True, capture_output=True, timeout=timeout, check=False)
    if result.stdout:
        print(redact(result.stdout.rstrip()))
    if result.stderr:
        print(redact(result.stderr.rstrip()), file=sys.stderr)
    print(f"exit_code={result.returncode}")
    if required and result.returncode != 0:
        raise VerificationFailure(f"{label} failed with exit code {result.returncode}")
    return result


def request_json(
    method: str,
    path: str,
    *,
    payload: dict[str, Any] | None = None,
    admin: bool = False,
    key: str | None = None,
    expected: tuple[int, ...] = (200,),
) -> tuple[int, Any]:
    headers = {"Accept": "application/json"}
    body = None
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    if admin:
        api_key = ADMIN_API_KEY if key is None else key
        if api_key:
            headers["X-Admin-API-Key"] = api_key
    request = Request(f"{API_URL}{path}", data=body, headers=headers, method=method)
    try:
        with urlopen(request, timeout=10) as response:
            status = response.status
            raw = response.read().decode("utf-8")
    except HTTPError as exc:
        status = exc.code
        raw = exc.read().decode("utf-8")
    except URLError as exc:
        raise VerificationFailure(f"{method} {path} failed to connect: {exc}") from exc
    if status not in expected:
        raise VerificationFailure(f"{method} {path} returned HTTP {status}: {redact(raw[:500])}")
    return status, json.loads(raw) if raw else {}


def request_text(url: str) -> tuple[int, str]:
    try:
        with urlopen(url, timeout=10) as response:
            return response.status, response.read().decode("utf-8", errors="replace")
    except HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", errors="replace")
    except URLError as exc:
        raise VerificationFailure(f"GET {url} failed to connect: {exc}") from exc


def page_total(path: str) -> int:
    _, body = request_json("GET", path)
    if isinstance(body, dict) and isinstance(body.get("total"), int):
        return int(body["total"])
    if isinstance(body, list):
        return len(body)
    raise VerificationFailure(f"{path} returned unsupported collection shape")


def poll(label: str, check) -> Any:  # type: ignore[no-untyped-def]
    deadline = time.monotonic() + TIMEOUT_SECONDS
    last_error = "not evaluated"
    while time.monotonic() < deadline:
        try:
            value = check()
            if value:
                print(f"{label}: ok")
                return value
        except Exception as exc:  # noqa: BLE001
            last_error = str(exc)
        time.sleep(3)
    raise VerificationFailure(f"Timed out waiting for {label}: {last_error}")


def require_clean_confirmation() -> None:
    print(
        "\nWARNING: this will run 'docker compose down -v'. It deletes only this Compose project's "
        "Docker volumes, including the local PostgreSQL demo database volume. It does not delete "
        "source files, .git, .env, model artifacts, or unrelated Docker volumes."
    )
    confirmation = input("Type DELETE_PROJECT_POSTGRES_VOLUME to continue: ").strip()
    if confirmation != "DELETE_PROJECT_POSTGRES_VOLUME":
        raise VerificationFailure("clean database verification cancelled")


def parse_ps(output: str) -> list[dict[str, Any]]:
    text = output.strip()
    if not text:
        return []
    try:
        value = json.loads(text)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
        if isinstance(value, dict):
            return [value]
    except json.JSONDecodeError:
        rows = []
        for line in text.splitlines():
            try:
                value = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(value, dict):
                rows.append(value)
        if rows:
            return rows

        rows = []
        for line in text.splitlines()[1:]:
            fields = line.split()
            if fields:
                rows.append({"Name": fields[0], "State": " ".join(fields[1:])})
        return rows
    return []


def verify_compose_state() -> list[dict[str, Any]]:
    result = run_command("compose ps", ["docker", "compose", "ps", "-a", "--format", "json"], timeout=120)
    states = parse_ps(result.stdout)
    seen = {str(item.get("Service") or item.get("Name")): item for item in states}
    missing = [service for service in SERVICES if service not in seen and not any(service in key for key in seen)]
    if missing:
        raise VerificationFailure(f"Missing compose services in ps output: {missing}")
    restarting = [item for item in states if "restart" in json.dumps(item).lower()]
    if restarting:
        raise VerificationFailure(f"Service restart loop suspected: {restarting}")
    return states


def verify_logs() -> dict[str, str]:
    findings: dict[str, str] = {}
    bad_patterns = re.compile(r"DuplicateObject|ModuleNotFoundError|Traceback|permission denied|restart loop", re.IGNORECASE)
    for service in SERVICES:
        result = run_command(
            f"logs {service}",
            ["docker", "compose", "logs", service, "--tail=200"],
            timeout=120,
            required=False,
        )
        combined = f"{result.stdout}\n{result.stderr}"
        match = bad_patterns.search(combined)
        findings[service] = "suspicious_log_match" if match else "no_blocking_pattern"
    return findings


def verify_api_contracts() -> dict[str, Any]:
    evidence: dict[str, Any] = {}
    paths = [
        "/",
        "/health",
        "/ready",
        "/openapi.json",
        "/api/devices",
        "/api/security-events",
        "/api/detections",
        "/api/risks/current",
        "/api/policy-decisions",
        "/api/response-actions",
        "/api/quarantine",
        "/api/audit-logs",
    ]
    for path in paths:
        status, body = request_json("GET", path)
        evidence[path] = {"status": status, "shape": type(body).__name__}

    _, openapi = request_json("GET", "/openapi.json")
    security_schemes = openapi.get("components", {}).get("securitySchemes", {})
    health_schema = openapi.get("components", {}).get("schemas", {}).get("HealthResponse", {})
    if "APIKeyHeader" not in security_schemes:
        raise VerificationFailure("OpenAPI security scheme APIKeyHeader is missing")
    if "additionalProperties" in health_schema:
        raise VerificationFailure("HealthResponse schema is generic")

    _, devices = request_json("GET", "/api/devices")
    if not isinstance(devices, list):
        raise VerificationFailure("/api/devices did not return a list")
    evidence["device_count"] = len(devices)
    telemetry_total = 0
    for device in devices:
        device_id = str(device["id"])
        telemetry_total += page_total(f"/api/devices/{quote(device_id)}/telemetry")
    evidence["telemetry_count"] = telemetry_total

    _, risks = request_json("GET", "/api/risks/current")
    for row in risks:
        risk = row.get("risk")
        if risk is not None and not 0 <= int(risk["risk_score"]) <= 100:
            raise VerificationFailure(f"Risk score out of range for {row.get('device_id')}")
    evidence["risk_count"] = len(risks)

    _, detections = request_json("GET", "/api/detections")
    for item in detections.get("items", []):
        score = float(item["anomaly_score"])
        if not 0.0 <= score <= 1.0:
            raise VerificationFailure(f"Anomaly score out of range: {score}")

    for name, path in API_COLLECTIONS.items():
        evidence[f"{name}_count"] = page_total(path)
    evidence["quarantine_count"] = len(request_json("GET", "/api/quarantine")[1])
    return evidence


def verify_authentication() -> dict[str, Any]:
    if not ADMIN_API_KEY:
        raise VerificationFailure("ADMIN_API_KEY is missing from .env")
    evidence: dict[str, Any] = {}
    attack_payload = {"device_id": "camera-01", "intensity": 5, "seed": 42}
    manual_payload = {"reason": "foundation verification"}
    checks = [
        ("missing_attack_start", "POST", "/api/simulations/attacks/mqtt_flood/start", attack_payload, False, None, 401),
        ("wrong_attack_start", "POST", "/api/simulations/attacks/mqtt_flood/start", attack_payload, True, "incorrect-key", 403),
        ("unknown_scenario", "POST", "/api/simulations/attacks/external_scan/start", attack_payload, True, None, 422),
        ("excessive_intensity", "POST", "/api/simulations/attacks/mqtt_flood/start", {"device_id": "camera-01", "intensity": 101, "seed": 42}, True, None, 422),
        ("missing_manual_quarantine", "POST", "/api/admin/devices/camera-01/quarantine", manual_payload, False, None, 401),
        ("wrong_manual_restore", "POST", "/api/admin/devices/camera-01/restore", manual_payload, True, "incorrect-key", 403),
    ]
    for name, method, path, payload, admin, key, expected in checks:
        status, _ = request_json(method, path, payload=payload, admin=admin, key=key, expected=(expected,))
        evidence[name] = status

    status, body = request_json(
        "POST",
        "/api/simulations/attacks/mqtt_flood/start",
        payload=attack_payload,
        admin=True,
    )
    if body.get("status") != "started":
        raise VerificationFailure(f"valid safe attack did not start: {body}")
    evidence["valid_attack_start"] = status
    stop_status, _ = request_json("POST", "/api/simulations/attacks/mqtt_flood/stop", admin=True)
    evidence["valid_attack_stop"] = stop_status
    return evidence


def verify_dashboard() -> dict[str, Any]:
    status, html = request_text(DASHBOARD_URL)
    if status != 200:
        raise VerificationFailure(f"Dashboard returned HTTP {status}")
    if 'id="root"' not in html:
        raise VerificationFailure("Dashboard root element is missing")
    asset_refs = re.findall(r'src="([^"]+\\.js)"|href="([^"]+\\.css)"', html)
    assets_checked = 0
    for js_ref, css_ref in asset_refs:
        ref = js_ref or css_ref
        asset_status, asset_text = request_text(f"{DASHBOARD_URL}{ref}")
        if asset_status != 200:
            raise VerificationFailure(f"Dashboard asset {ref} returned HTTP {asset_status}")
        if "http://api:8000" in asset_text:
            raise VerificationFailure("Dashboard asset references Docker-only API host http://api:8000")
        assets_checked += 1
    return {"http_status": status, "assets_checked": assets_checked, "visual_verification": "manual_browser_required"}


def main() -> int:
    parser = argparse.ArgumentParser(description="Run clean runtime verification for the local Compose IoT lab.")
    parser.add_argument("--clean", action="store_true", help="Prompt, then delete this Compose project's Docker volumes first.")
    args = parser.parse_args()

    evidence: dict[str, Any] = {}
    try:
        run_command("docker info", ["docker", "info"], timeout=120)
        if args.clean:
            require_clean_confirmation()
            run_command("clean compose volumes", ["docker", "compose", "down", "-v"], timeout=180)

        run_command("compose build no cache", ["docker", "compose", "build", "--no-cache"], timeout=1800)
        run_command("start postgres and mosquitto", ["docker", "compose", "up", "-d", "postgres", "mosquitto"], timeout=300)
        run_command("first migration", ["make", "migrate"], timeout=600)
        run_command("second migration", ["make", "migrate"], timeout=600)
        run_command("migration head check", ["make", "migration-check"], timeout=300)
        run_command("start full stack", ["docker", "compose", "up", "-d"], timeout=600)
        evidence["compose_states"] = verify_compose_state()
        evidence["logs"] = verify_logs()
        run_command("first demo", ["make", "demo"], timeout=900)
        run_command("second demo", ["make", "demo"], timeout=900)
        run_command("post-demo migration head check", ["make", "migration-check"], timeout=300)
        evidence["api"] = verify_api_contracts()
        evidence["auth"] = verify_authentication()
        run_command("smoke test", ["make", "smoke"], timeout=300)
        evidence["post_smoke_api"] = verify_api_contracts()
        evidence["dashboard"] = verify_dashboard()
        print("\nFOUNDATION_RUNTIME_VERIFY_RESULT=PASS")
        print(json.dumps(evidence, indent=2, sort_keys=True, default=str))
        print("\nManual step: open http://localhost:5173 and confirm visual rendering and no console errors.")
        return 0
    except (VerificationFailure, subprocess.TimeoutExpired) as exc:
        print("\nFOUNDATION_RUNTIME_VERIFY_RESULT=FAIL", file=sys.stderr)
        print(redact(str(exc)), file=sys.stderr)
        if evidence:
            print(json.dumps(evidence, indent=2, sort_keys=True, default=str))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
