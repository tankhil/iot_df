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
- Backend and dashboard containers run as non-root users.
- The dashboard production image serves built static files and must not run the Vite development or preview server.
- Runtime images should not include test, lint, audit, or build toolchains unless a service explicitly needs them.
- `.dockerignore` excludes local secrets, virtualenvs, generated model artifacts, database dumps, and build output from Docker build contexts.

## Dependency And Supply-Chain Policy

Run dependency checks before merging dependency, container, or CI changes:

```bash
make dependency-lock-check
pip-audit -r backend/requirements.lock
pip-audit --local --skip-editable
cd dashboard && npm audit --omit=dev --audit-level=moderate
cd dashboard && npm audit --audit-level=moderate
```

Classify findings as runtime or development-only. Runtime findings in the API,
collector, simulator, dashboard static server, Docker base images, or GitHub
Actions must be remediated promptly with the smallest compatible update.
Development-only findings in local test, lint, build, or preview tooling should
also be remediated when compatible fixes exist. Do not hide vulnerabilities by
moving vulnerable packages between dependency groups or suppressing audits
without documenting exploitability and a follow-up owner.

Use `npm audit fix` only after reviewing the proposed diff. Do not use forced
npm audit remediation for this repository. Do not apply breaking major
upgrades unless a vulnerability fix, ecosystem support window, or documented
migration need justifies the change and the full verification workflow passes.

Dependabot is configured for Python, npm, Docker, and GitHub Actions. Review
automated dependency PRs with the same runtime/development classification and
verification requirements.

Runtime OS vulnerability scanning must keep unfixed findings visible. CI reports
all OS findings with unfixed findings included, and separately fails on fixed
high/critical runtime OS vulnerabilities where Trivy can distinguish fixed
versions reliably. The current reviewed OS finding list and Docker reproducibility
tradeoff are recorded in `docs/dependency-security-review.md`.

## Reporting

Never commit real credentials, private keys, certificates, database dumps, or telemetry from networks outside this lab. Use `.env.example` only for placeholders, and keep real local values in `.env` or another ignored environment-specific file.

If a credential is exposed in Git history, logs, screenshots, issues, or pull requests, rotate it immediately and treat the old value as compromised.

Report vulnerabilities privately to the repository owner when possible. If a public issue is necessary for portfolio/demo use, describe the affected component without including real secrets, real device identifiers, exploit payloads for external systems, or data from networks outside this lab.
