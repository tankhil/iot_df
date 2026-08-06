.PHONY: setup up migrate migration-check train test lint git-safety demo smoke verify down compose-config frontend-build docker-build clean-db-reset

setup:
	cp -n .env.example .env
	python3 -m venv .venv
	.venv/bin/python -m pip install -e 'backend[dev]'
	cd dashboard && npm install

up:
	docker compose up --build

migrate:
	docker compose run --rm migrate

migration-check:
	docker compose run --rm migrate python /workspace/scripts/migration_check.py

train:
	docker compose run --rm api python /workspace/scripts/train_model.py

test:
	.venv/bin/python -m pytest -q backend/tests simulator/tests
	cd dashboard && npm run test

lint:
	.venv/bin/python -m ruff check backend/app backend/tests simulator scripts
	cd backend && ../.venv/bin/python -m mypy app
	cd dashboard && npm run lint

git-safety:
	.venv/bin/python scripts/git_safety_check.py

frontend-build:
	cd dashboard && npm run build

compose-config:
	docker compose config

demo:
	docker compose run --rm migrate
	docker compose run --rm api python /workspace/scripts/seed_demo_data.py
	docker compose run --rm api python /workspace/scripts/train_model.py
	docker compose run --rm api python /workspace/scripts/evaluate_model.py

smoke:
	ADMIN_API_KEY=$$(grep -E '^ADMIN_API_KEY=' .env | cut -d= -f2-) .venv/bin/python scripts/e2e_smoke_test.py

verify:
	$(MAKE) compose-config
	$(MAKE) test
	$(MAKE) lint
	$(MAKE) frontend-build
	@if docker compose ps --services --filter status=running 2>/dev/null | grep -q '^api$$'; then \
		$(MAKE) migration-check; \
		$(MAKE) smoke; \
	else \
		echo "Skipping runtime checks: Docker stack is not running or Docker is unavailable."; \
	fi

docker-build:
	docker compose build

clean-db-reset:
	@echo "WARNING: this deletes the local PostgreSQL Docker volume and all demo data."
	@printf "Type DELETE_DEMO_DATA to continue: "; \
	read confirmation; \
	if [ "$$confirmation" = "DELETE_DEMO_DATA" ]; then \
		docker compose down -v; \
	else \
		echo "Cancelled."; \
		exit 1; \
	fi

down:
	docker compose down
