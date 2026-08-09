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
- Quarantine, restore, and firewall-like responses are simulated application state transitions only.

## Recovery Safety Conditions

Automatic quarantine requires repeated critical/high-risk confirmation windows. Automatic restore requires the device to be currently quarantined, the simulated quarantine action to have completed, the minimum quarantine duration and cooldown to have elapsed, and three consecutive trusted low-risk recovery observations with no newer high/critical evidence. Trust is not inferred from MQTT/API payload fields, topics, device IDs, event types, or missing features; ordinary telemetry cannot mark itself as a recovery probe. Idempotency keys suppress replayed recovery probes and duplicate restore actions.

The runtime verification target `make smoke-quarantine` proves this simulated state machine end to end:

`normal/active -> suspicious/high/critical -> quarantine pending -> quarantined -> recovery observation -> restored/active`

This is evidence that the local simulation and policy engine behave correctly. It is not evidence that real network equipment, firewalls, or physical IoT devices are controlled.

## Limitations

The platform does not protect real devices, enforce real network controls, or replace production security monitoring.
