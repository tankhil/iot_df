from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_backend_dockerfile_uses_portable_non_root_user_args() -> None:
    dockerfile = (ROOT / "backend" / "Dockerfile").read_text(encoding="utf-8")

    assert "ARG APP_UID=1000" in dockerfile
    assert "ARG APP_GID=1000" in dockerfile
    assert "useradd --create-home --uid 1000" not in dockerfile
    assert '--uid "${APP_UID}"' in dockerfile
    assert '--gid "${APP_GID}"' in dockerfile
    assert 'getent group "${APP_GID}"' in dockerfile
    assert "USER ${APP_UID}:${APP_GID}" in dockerfile
    assert "chmod 777" not in dockerfile


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

    assert "privileged:" not in compose
    assert "/var/run/docker.sock" not in compose
    assert "chmod 777" not in compose
