# Data Flow

1. Simulated devices publish MQTT telemetry to `iot/{device_id}/telemetry`.
2. Collector validates JSON payloads with Pydantic.
3. Devices are upserted and telemetry/security events are persisted.
4. Feature extraction creates a time-windowed feature row.
5. Detection loads the active device-type model or global model.
6. Risk scoring combines ML and deterministic security signals.
7. Policy chooses allow-listed simulated actions.
8. Response executor records actions and updates quarantine state.
9. API and dashboard expose current status, alerts, and audit history.

Quarantined devices have normal telemetry marked denied by quarantine, while health-check events remain processable.
