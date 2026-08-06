# Contributing

Thank you for improving the AI Adaptive IoT Defense Platform. Keep contributions defensive, reproducible, and safe for a public portfolio repository.

## Local Setup

Requirements:

- Python 3.12 or newer.
- Node.js 20 or newer.
- Docker and Docker Compose for runtime/demo checks.

Set up local dependencies:

```bash
make setup
make compose-config
```

`make setup` creates `.env` from `.env.example`, creates `.venv`, installs backend development dependencies, and installs dashboard dependencies. Replace the local demo admin key before sharing any environment.

## Development Workflow

Create a focused branch for each change:

```bash
git checkout -b feature/short-description
```

Keep commits small and descriptive. Use imperative commit messages, for example:

```text
Add deterministic policy tests
Fix dashboard empty-state rendering
```

Do not commit `.env`, virtual environments, `node_modules`, `dashboard/dist`, Docker volume data, logs, caches, backups, or generated model artifacts.

## Tests And Linting

Run the core checks before opening a pull request:

```bash
make test
make lint
make frontend-build
make compose-config
git diff --check
```

When Docker is available and the stack is running, also run:

```bash
make migration-check
make smoke
```

Use `make verify` for the full non-destructive local verification workflow. It runs runtime checks only when the Compose stack is already available.

## Demo Runtime

Start the local lab in order:

```bash
docker compose up -d postgres mosquitto
make migrate
docker compose up -d
make demo
```

All attacks, devices, quarantine actions, and recovery actions are simulated. Do not add functionality that scans external networks, modifies host firewalls, mounts the Docker socket, or runs privileged containers.

## Security Reporting

Do not publish real secrets, real device identifiers, or external network data in issues, commits, screenshots, or logs.

For this portfolio repository, report security findings privately to the repository owner when possible, or open a minimal issue that describes the affected component without including sensitive values. See `SECURITY.md` for project scope and safety constraints.
