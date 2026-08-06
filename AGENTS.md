# Repository Guide

## Layout

- `backend/app`: FastAPI, SQLAlchemy models, MQTT collector, feature extraction, detection, risk, policy, response modules.
- `backend/alembic`: Database migrations.
- `backend/tests`: Backend unit/API tests.
- `simulator`: Device profiles and safe attack simulations.
- `dashboard`: React + TypeScript dashboard.
- `scripts`: Demo, training, and evaluation commands.
- `docs`: Architecture and research notes.

## Commands

- `make setup`: create `.env` and install dashboard dependencies.
- `make up`: start the Docker Compose stack; the API waits for the migration service.
- `make migrate`: run Alembic migrations through the dedicated migration container.
- `make migration-check`: verify the database Alembic revision equals the migration head.
- `make train`: train Isolation Forest model from stored feature windows.
- `make test`: run Python tests.
- `make lint`: run Ruff, mypy, and dashboard type checks.
- `make frontend-build`: build dashboard production bundle.
- `make demo`: run migrations, seed deterministic synthetic demo data, train, and evaluate.
- `make smoke`: run the bounded localhost E2E smoke test against a running stack.
- `make verify`: run non-destructive local verification and runtime checks when the stack is available.
- `make down`: stop containers without deleting data.
- `make clean-db-reset`: destructive reset that prompts before deleting the PostgreSQL Docker volume.

## Startup Order

Clean local setup:

1. `make setup`
2. `make compose-config`
3. `docker compose up -d postgres mosquitto`
4. `make migrate`
5. `docker compose up -d`
6. `make demo`

Normal daily startup:

1. `docker compose up -d`
2. `make migrate`
3. `make demo` when fresh synthetic data/model artifacts are needed.

API URL: `http://localhost:8000`; OpenAPI: `http://localhost:8000/docs`; dashboard: `http://localhost:5173`.
Admin-only endpoints require `X-Admin-API-Key` from `.env`; do not print or commit the key.

## Engineering Conventions

- Keep ML inference, risk scoring, policy decisions, and responses separate.
- ML must never directly authorize quarantine.
- Add only allow-listed response actions.
- Use UTC timestamps internally.
- Keep audit records append-only in normal application flows.
- Prefer small deterministic tests for security-critical logic.
- Alembic is the only runtime schema owner; do not add `Base.metadata.create_all`.
- Demo seeding must stay repeatable and report created/updated/skipped records.

## Security Restrictions

- No external scanning or attacks.
- No host firewall changes.
- No Docker socket mounts.
- No privileged containers.
- No arbitrary shell command generation.
- No plaintext secrets in committed files.
- No normal Make target may delete Docker volumes or user data.

## Troubleshooting

| Symptom | Diagnostic command | Safe resolution |
| --- | --- | --- |
| Docker permission denied | `docker compose ps` | Run from a Docker-enabled shell or fix the local Docker group/session. |
| Migration duplicate enum/type error | `docker compose logs migrate --tail=200` | Rebuild the API image; use `make clean-db-reset` only after confirming demo data deletion. |
| API reports not ready | `curl -i http://localhost:8000/ready` | Start PostgreSQL, then run `make migrate`, then start application services. |
| Dashboard blank or unavailable | `docker compose logs dashboard --tail=200` | Rebuild dashboard so `VITE_API_URL` points to `http://localhost:8000`. |
| Demo data repeats unexpectedly | `make demo` | Confirm the seed marker exists in audit logs and the database was not reset. |

Useful service logs:

```bash
docker compose logs postgres --tail=200
docker compose logs mosquitto --tail=200
docker compose logs migrate --tail=200
docker compose logs api --tail=200
docker compose logs collector --tail=200
docker compose logs simulator --tail=200
docker compose logs dashboard --tail=200
```

## Definition Of Done

Code should pass tests, Ruff, practical mypy, frontend build, and `docker compose config`. When Docker is available, migrations must be at head, `make demo` should be repeatable, and `make smoke` should pass. Security-sensitive behavior needs tests and audit records.
