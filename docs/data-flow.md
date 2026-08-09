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

Quarantined devices have normal telemetry marked denied by quarantine, while health-check events remain processable for visibility. Processable health-check telemetry is still untrusted: MQTT clients and public telemetry API callers cannot set a trusted recovery flag through payload fields, topics, device IDs, event types, or missing features.

Recovery is simulated through server-controlled recovery observations. An already quarantined device must have a completed simulated quarantine action, satisfy the minimum quarantine duration and cooldown, avoid newer high/critical evidence, and accumulate the required consecutive trusted low-risk observations before `restore_access` is selected. An already active device is not restored again, and an already quarantined device is not quarantined again by automatic policy.

State progression:

`normal/active -> suspicious/high/critical -> quarantine pending -> quarantined -> recovery observation -> restored/active`

All response actions are allow-listed application records. The platform does not run host firewall commands or real-device commands.
