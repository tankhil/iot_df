import importlib.util
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def load_lock_checker():
    spec = importlib.util.spec_from_file_location(
        "check_python_lock", ROOT / "scripts" / "check_python_lock.py"
    )
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules["check_python_lock"] = module
    spec.loader.exec_module(module)
    return module


def test_backend_dockerfile_uses_portable_non_root_user_args() -> None:
    dockerfile = (ROOT / "backend" / "Dockerfile").read_text(encoding="utf-8")

    assert "ARG APP_UID=1000" in dockerfile
    assert "ARG APP_GID=1000" in dockerfile
    assert (
        "FROM python:3.12.12-slim-bookworm@sha256:"
        "593bd06efe90efa80dc4eee3948be7c0fde4134606dd40d8dd8dbcade98e669c"
    ) in dockerfile
    assert "apt-get upgrade" not in dockerfile
    assert "useradd --create-home --uid 1000" not in dockerfile
    assert '--uid "${APP_UID}"' in dockerfile
    assert '--gid "${APP_GID}"' in dockerfile
    assert 'getent group "${APP_GID}"' in dockerfile
    assert "USER ${APP_UID}:${APP_GID}" in dockerfile
    assert "chmod 777" not in dockerfile
    assert "COPY backend/requirements.lock" in dockerfile
    assert "pip install --no-cache-dir --require-hashes -r /workspace/backend/requirements.lock" in dockerfile
    assert "COPY backend/build-requirements.lock" in dockerfile
    assert "pip install --no-cache-dir --require-hashes -r /workspace/backend/build-requirements.lock" in dockerfile
    assert "pip install --no-cache-dir --no-build-isolation --no-deps /workspace/backend" in dockerfile
    assert "pip uninstall -y setuptools" in dockerfile
    assert "requirements-dev.lock" not in dockerfile
    assert "/workspace/backend[dev]" not in dockerfile
    assert "pip-audit" not in dockerfile
    assert "pytest" not in dockerfile
    assert "ruff" not in dockerfile
    assert "mypy" not in dockerfile


def test_dashboard_dockerfile_serves_static_bundle_without_vite_runtime() -> None:
    dockerfile = (ROOT / "dashboard" / "Dockerfile").read_text(encoding="utf-8")

    assert "AS build" in dockerfile
    assert "npm ci" in dockerfile
    assert (
        "FROM node:20.19.5-bookworm-slim@sha256:"
        "9e70124bd00f47dd023e349cd587132ae61892acc0e47ed641416c3e18f401c3"
    ) in dockerfile
    assert (
        "FROM busybox:1.37.0-uclibc@sha256:"
        "8d7b1636e974e0adfd8d945955fca609304f0a56c18799dfd032d6e661382d84"
    ) in dockerfile
    assert "COPY --from=build" in dockerfile
    assert "USER 10002:10002" in dockerfile
    assert 'CMD ["httpd", "-f", "-p", "5173", "-h", "/www"]' in dockerfile
    assert 'CMD ["npm", "run", "preview"]' not in dockerfile
    assert "npm run dev" not in dockerfile
    final_stage = dockerfile.split("FROM busybox:", maxsplit=1)[1]
    assert "node" not in final_stage.lower()
    assert "npm" not in final_stage.lower()
    assert "vite" not in final_stage.lower()


def test_docker_context_excludes_test_directories() -> None:
    dockerignore = (ROOT / ".dockerignore").read_text(encoding="utf-8")

    assert "backend/tests/" in dockerignore
    assert "simulator/tests/" in dockerignore


def test_compose_forwards_host_uid_gid_to_backend_image_builds() -> None:
    compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")

    assert compose.count("dockerfile: backend/Dockerfile") == 4
    assert compose.count("APP_UID: ${LOCAL_UID:-1000}") == 4
    assert compose.count("APP_GID: ${LOCAL_GID:-1000}") == 4


def test_makefile_supplies_current_uid_gid_without_overriding_home() -> None:
    makefile = (ROOT / "Makefile").read_text(encoding="utf-8")

    assert "LOCAL_UID := $(shell id -u)" in makefile
    assert "LOCAL_GID := $(shell id -g)" in makefile
    assert "COMPOSE := LOCAL_UID=$(LOCAL_UID) LOCAL_GID=$(LOCAL_GID) docker compose" in makefile
    assert "HOME=" not in makefile


def test_compose_keeps_container_security_boundaries() -> None:
    compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")

    assert (
        "postgres:16.10-bookworm@sha256:"
        "38471f330eb885e04de130b768d6db4e10469e2311879c7e5c699f6d2d8a1c74"
    ) in compose
    assert (
        "eclipse-mosquitto:2.0.22@sha256:"
        "212f89e1eaeb2c322d6441b64396e3346026674db8fa9c27beac293405c32b3c"
    ) in compose
    assert "privileged:" not in compose
    assert "/var/run/docker.sock" not in compose
    assert "chmod 777" not in compose


def test_ci_uses_frozen_python_dependencies_and_audits() -> None:
    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")

    assert "pip install --require-hashes -r backend/requirements-dev.lock" in workflow
    assert "pip install --no-build-isolation --no-deps -e backend" in workflow
    assert "python scripts/check_python_lock.py" in workflow
    assert "pip-audit -r backend/requirements.lock" in workflow
    assert "pip-audit --local --skip-editable" in workflow
    assert "npm audit --omit=dev --audit-level=moderate" in workflow
    assert "npm audit --audit-level=moderate" in workflow
    assert "npm audit fix --force" not in workflow
    assert "ignore-unfixed: false" in workflow
    assert "ignore-unfixed: true" in workflow
    assert "severity: HIGH,CRITICAL" in workflow


def test_scanner_review_documents_unfixed_high_critical_os_findings() -> None:
    review = (ROOT / "docs" / "dependency-security-review.md").read_text(encoding="utf-8")

    assert "Review date: 2026-08-10" in review
    assert "24 high/critical backend OS findings" in review
    assert review.count("No fixed version reported by Trivy") == 24
    assert "ignore-unfixed: false" in review
    assert "ignore-unfixed: true" in review


def test_github_actions_are_sha_pinned_with_release_comments() -> None:
    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    uses_refs = re.findall(r"^\s*uses:\s*([^@\s]+)@([0-9a-f]{40})\s*$", workflow, re.MULTILINE)

    assert uses_refs
    assert len(uses_refs) == workflow.count("uses:")
    assert "# actions/checkout v4.4.0" in workflow
    assert "# actions/setup-python v5.6.0" in workflow
    assert "# actions/setup-node v4.4.0" in workflow
    assert "# aquasecurity/trivy-action v0.36.0" in workflow


def test_python_locks_are_hash_pinned() -> None:
    for lockfile in (
        ROOT / "backend" / "requirements.lock",
        ROOT / "backend" / "build-requirements.lock",
        ROOT / "backend" / "requirements-dev.lock",
    ):
        text = lockfile.read_text(encoding="utf-8")
        assert "This file was autogenerated by uv" in text
        assert "--hash=sha256:" in text
        assert "adaptive-iot-defense-backend" not in {
            line.partition("==")[0] for line in text.splitlines() if "==" in line
        }
    assert "pip-audit==" not in (ROOT / "backend" / "requirements.lock").read_text(encoding="utf-8")
    assert "setuptools==" not in (ROOT / "backend" / "requirements.lock").read_text(encoding="utf-8")
    assert "setuptools==" in (ROOT / "backend" / "build-requirements.lock").read_text(encoding="utf-8")
    assert "uv==" in (ROOT / "backend" / "requirements-dev.lock").read_text(encoding="utf-8")


def test_python_lock_checker_detects_stale_and_missing_locks(tmp_path: Path) -> None:
    checker = load_lock_checker()
    generated = tmp_path / "generated.lock"
    generated.write_text("package==1.0\n", encoding="utf-8")

    missing_spec = checker.LockSpec("runtime", tmp_path / "missing.lock", ())
    assert checker.lock_is_current(missing_spec, generated) is False

    stale = tmp_path / "stale.lock"
    stale.write_text("package==0.9\n", encoding="utf-8")
    stale_spec = checker.LockSpec("runtime", stale, ())
    assert checker.lock_is_current(stale_spec, generated) is False

    current = tmp_path / "current.lock"
    current.write_text("package==1.0\n", encoding="utf-8")
    current_spec = checker.LockSpec("runtime", current, ())
    assert checker.lock_is_current(current_spec, generated) is True


def test_dependabot_covers_dependency_ecosystems() -> None:
    config = (ROOT / ".github" / "dependabot.yml").read_text(encoding="utf-8")

    assert 'package-ecosystem: "pip"' in config
    assert 'directory: "/backend"' in config
    assert 'package-ecosystem: "npm"' in config
    assert 'directory: "/dashboard"' in config
    assert config.count('package-ecosystem: "docker"') == 3
    assert 'package-ecosystem: "github-actions"' in config


def test_no_npm_audit_force_is_used() -> None:
    for path in (ROOT / "dashboard" / "package.json", ROOT / ".github" / "workflows" / "ci.yml"):
        text = path.read_text(encoding="utf-8")
        assert "npm audit fix --force" not in text
