# API Guide

The API is a local FastAPI service for the simulated defensive IoT lab. Do not expose the demo stack directly to the internet.

Base URL:

```text
http://localhost:8000
```

Interactive OpenAPI documentation:

```text
http://localhost:8000/docs
```

## System Endpoints

- `GET /`: Returns service name, version, status, and links to health, readiness, and docs.
- `GET /health`: Liveness check for the FastAPI process.
- `GET /ready`: Readiness check for required runtime dependencies. It verifies database access and returns `503` when a dependency is unavailable.
- `GET /openapi.json`: Machine-readable OpenAPI schema.

## Main Read-Only Endpoints

- `GET /api/devices`: Lists simulated IoT devices.
- `GET /api/devices/{device_id}`: Returns inventory, current risk, and quarantine state for one simulated device.
- `GET /api/devices/{device_id}/telemetry`: Returns paginated telemetry for one device.
- `GET /api/security-events`: Returns paginated simulated security events.
- `GET /api/detections`: Returns paginated anomaly detection records.
- `GET /api/risks/current`: Returns the latest risk state for each simulated device.
- `GET /api/alerts`: Returns recent suspicious-or-higher risk assessments.
- `GET /api/policy-decisions`: Returns deterministic policy decisions and selected actions.
- `GET /api/response-actions`: Returns simulated response actions.
- `GET /api/quarantine`: Returns simulated quarantine and recovery state.
- `GET /api/audit-logs`: Returns append-only application audit records.
- `GET /api/models`: Returns saved model metadata. Model artifact files are not exposed.

These endpoints are designed for dashboard and demo inspection. Collections use predictable JSON shapes and paginated endpoints include `items`, `total`, `limit`, and `offset`.

## Telemetry Ingestion

`POST /api/telemetry` accepts validated simulated telemetry and runs one detection, risk, policy, and response cycle.

Example shape:

```json
{
  "device_id": "camera-01",
  "device_type": "smart_camera",
  "timestamp": "2026-01-01T00:00:00Z",
  "topic": "iot/devices/camera-01/telemetry",
  "message_size": 256,
  "destination": "local-controller",
  "auth_success": true,
  "value": 0.5
}
```

Use only simulated device data. Do not send telemetry from real external networks or real devices unless the project is deliberately extended for that purpose with appropriate safeguards.

## Protected Admin Endpoints

Admin endpoints require the `X-Admin-API-Key` request header:

```text
X-Admin-API-Key: <local value from .env>
```

Do not commit or share the actual key.

Protected endpoints:

- `POST /api/simulations/attacks/{scenario}/start`: Starts an allow-listed safe attack simulation.
- `POST /api/simulations/attacks/{scenario}/stop`: Stops an allow-listed safe attack simulation.
- `POST /api/admin/devices/{device_id}/quarantine`: Manually applies simulated quarantine.
- `POST /api/admin/devices/{device_id}/restore`: Manually restores simulated access.

Allow-listed simulation scenarios include:

- `mqtt_flood`
- `auth_failures`
- `unauthorized_topic`
- `unknown_destination`

Admin operations are simulated. They do not change host firewall rules, run shell commands, scan networks, or control real devices.

## Authentication Responses

- `401 Unauthorized`: The admin API key header is missing.
- `403 Forbidden`: The admin API key header is present but invalid.
- `422 Unprocessable Entity`: The request path, scenario, or body failed validation.

Swagger UI supports the admin header through the Authorize button. Enter only a local demo key from `.env`.
