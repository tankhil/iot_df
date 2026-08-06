# Threat Model

## Scope

This project models defensive monitoring of simulated IoT devices in an isolated Docker network.

## Simulated Threats

- MQTT message flooding.
- Repeated authentication failures.
- Unauthorized MQTT topic access.
- Unknown simulated destination.

## Assets

- Simulated telemetry.
- Security events.
- Feature windows.
- Model artifacts.
- Risk assessments.
- Policy decisions.
- Response actions.
- Quarantine states.
- Audit logs.

## Trust Boundaries

- MQTT payloads are untrusted and validated before persistence.
- ML output is untrusted for authorization decisions.
- Admin endpoints require local API-key authentication.
- Docker services communicate only inside the lab network except API/dashboard ports exposed for local demo.

## Limitations

The platform does not protect real devices, enforce real network controls, or replace production security monitoring.
