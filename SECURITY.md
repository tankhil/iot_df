# Security Policy

## Defensive Scope

This repository is a defensive educational lab. All devices, attacks, quarantine actions, and recovery actions are simulated inside Docker Compose.

The project must not:

- Scan external networks.
- Exploit real devices.
- Modify host firewall rules.
- Mount the Docker socket.
- Use host networking.
- Run privileged containers.
- Store plaintext secrets.
- Generate arbitrary shell or firewall commands from ML output.

## Threat Model

Protected assets:

- Simulated telemetry and security events.
- Model artifacts.
- Policy decisions and audit trail.
- Local admin API key.

Main demo threats:

- MQTT flooding.
- Repeated auth failures.
- Unauthorized topic access.
- Unknown simulated destination.

Out of scope:

- Real malware.
- Persistence.
- Credential theft.
- Real network exploitation.
- Cloud deployment.
- Kubernetes.

## Controls

- PostgreSQL is internal to the Compose network.
- Admin endpoints require `X-Admin-API-Key`.
- Sensitive endpoints have in-memory rate limiting.
- CORS is restricted by environment configuration.
- SQL access uses SQLAlchemy ORM operations.
- Response execution is constrained to an action allow-list.
- Quarantine is simulated in application state.
- Audit logs are append-only at the application layer.

## Reporting

Never commit real credentials, private keys, certificates, database dumps, or telemetry from networks outside this lab. Use `.env.example` only for placeholders, and keep real local values in `.env` or another ignored environment-specific file.

If a credential is exposed in Git history, logs, screenshots, issues, or pull requests, rotate it immediately and treat the old value as compromised.

Report vulnerabilities privately to the repository owner when possible. If a public issue is necessary for portfolio/demo use, describe the affected component without including real secrets, real device identifiers, exploit payloads for external systems, or data from networks outside this lab.
