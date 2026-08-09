# Demo Guide

This guide runs the local AI Adaptive IoT Defense Platform demo. Devices, attacks, quarantine, recovery, and telemetry are simulated inside Docker Compose. The project does not scan, attack, contact, or modify external systems.

## Environment Setup

Install prerequisites:

- Python 3.12 or newer.
- Node.js 20 or newer.
- Docker and Docker Compose.

Create local configuration and install dependencies:

```bash
make setup
make disk-check
make compose-config
```

`make setup` creates `.env` from `.env.example`. Keep the admin API key local, do not commit `.env`, and do not paste the key into issues, logs, or screenshots.

The backend image accepts `APP_UID` and `APP_GID` build arguments. Make targets create the project `models/` directory as the host user and pass the current host IDs through Compose as `LOCAL_UID=$(id -u)` and `LOCAL_GID=$(id -g)`, which keeps the `models/` bind mount writable by non-root backend containers on hosts where the user is not UID 1000. If you build directly with Docker Compose, export or prefix those values yourself.

## Startup Order

Start PostgreSQL and Mosquitto first:

```bash
docker compose up -d postgres mosquitto
```

Run database migrations:

```bash
make migrate
```

Start the rest of the stack:

```bash
docker compose up -d
```

The API waits for the migration service before it starts. The collector and dashboard wait for the API health check.

## Migrations

Alembic owns the runtime schema. Apply migrations with:

```bash
make migrate
```

Check that the database revision matches the Alembic head:

```bash
make migration-check
```

The migration command is expected to be idempotent; running it a second time should not recreate schema objects.

## Demo Data And Model Training

Seed deterministic synthetic telemetry, train Isolation Forest models, and run the preliminary evaluation:

```bash
make demo
```

The demo seed is repeatable. A second run should report skipped existing seed records instead of duplicating the deterministic baseline.

Model training is fingerprinted from the model type, global or device-type scope, ordered feature schema and schema version, deterministic training-dataset hash, normalized hyperparameters, random seed, training-code version, and model artifact format version. If the fingerprint and artifact are unchanged, training reuses the existing `model_versions` row and artifact. If the same fingerprint has a missing or corrupt artifact, training rebuilds the artifact and updates the same metadata row. Changed data, seed, schema, hyperparameters, or training-code identity creates a new model version.

Generated model artifacts are written under `models/` and are intentionally ignored by Git.

The evaluation output is a preliminary synthetic demo signal. An F1 score of `1.0` on the toy dataset is not production evidence and must not be treated as a real-world model-quality claim.

## Disk Preflight

Docker-heavy verification can consume several GiB, especially when building images without cache. Keep at least 8 GiB free on both the project filesystem and Docker data filesystem.

Run the non-destructive disk preflight before Docker-heavy work:

```bash
make disk-check
```

The preflight uses Python `shutil.disk_usage`, reports total, used, free, and percentage for the project filesystem and Docker data filesystem when Docker is accessible. It fails below 5 GiB free, warns from 5 GiB to under 8 GiB, and passes at 8 GiB or more. It never deletes files, images, containers, build cache, or volumes.

For diagnostic output only:

```bash
make disk-usage
```

Manual cleanup candidates, when you decide cleanup is appropriate:

- `docker system df`: shows Docker image, container, volume, and build-cache usage.
- `docker builder prune`: deletes unused Docker build cache only.
- `docker image prune`: deletes dangling untagged Docker images only.
- `docker system prune`: deletes stopped containers, unused networks, dangling images, and build cache; it does not delete volumes unless `--volumes` is added.
- `docker volume prune`: deletes all unused local Docker volumes, including database volumes from other projects if they are unused.

## Safe Attack Simulation

Safe attack simulations produce synthetic telemetry and security signals only inside the local lab. They do not perform network scanning or exploitation.

Run examples from inside the Compose network:

```bash
docker compose run --rm api python /workspace/scripts/demo_safe_attack.py mqtt_flood --device-id camera-01 --intensity 40
docker compose run --rm api python /workspace/scripts/demo_safe_attack.py auth_failures --device-id lock-01
docker compose run --rm api python /workspace/scripts/demo_safe_attack.py unauthorized_topic --device-id camera-01
docker compose run --rm api python /workspace/scripts/demo_safe_attack.py unknown_destination --device-id camera-01
```

Admin-controlled simulation endpoints require `X-Admin-API-Key`; use the key from your local `.env` without committing or sharing it.

## URLs

- API root: `http://localhost:8000`
- OpenAPI docs: `http://localhost:8000/docs`
- API health: `http://localhost:8000/health`
- API readiness: `http://localhost:8000/ready`
- Dashboard: `http://localhost:5173`

## Verification

Run the non-destructive local verification workflow:

```bash
make verify
```

If the Docker stack is running, `make verify` also runs the migration head check and E2E smoke test. If the stack is not running, start it before relying on runtime results.

To prove the full simulated quarantine and automatic recovery path against a running local stack:

```bash
make smoke-quarantine
```

This bounded E2E check uses one simulated device, starts one allow-listed safe attack through the authenticated API, submits project-local attack telemetry through public API boundaries, verifies exactly one automatic simulated quarantine, then submits three authenticated control-plane recovery probes before exactly one automatic restore. Ordinary MQTT or public API telemetry cannot mark a recovery observation trusted. The check never recreates containers, deletes volumes, changes host firewall rules, or contacts external targets.

The intended state machine is:

`normal/active -> suspicious/high/critical -> quarantine pending -> quarantined -> recovery observation -> restored/active`

## Shutdown

Stop containers without deleting demo data:

```bash
make down
```

Use the destructive reset only when you intentionally want to delete the local PostgreSQL demo volume:

```bash
make clean-db-reset
```

The reset target prompts before deleting data.

## Troubleshooting

Check service state:

```bash
docker compose ps -a
```

Useful logs:

```bash
docker compose logs postgres --tail=200
docker compose logs mosquitto --tail=200
docker compose logs migrate --tail=200
docker compose logs api --tail=200
docker compose logs collector --tail=200
docker compose logs simulator --tail=200
docker compose logs dashboard --tail=200
```

Common fixes:

- API is not ready: start PostgreSQL, run `make migrate`, then start the full stack.
- Dashboard is blank: verify `http://localhost:8000/health`, rebuild the dashboard image, and confirm `VITE_API_URL` points to `http://localhost:8000`.
- Migration duplicate type error: rebuild the backend image; use `make clean-db-reset` only after confirming local demo data can be deleted.
- Docker permission denied: run from a Docker-enabled shell or fix the local Docker group/session.
