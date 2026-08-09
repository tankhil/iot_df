FROM python:3.12.6-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/workspace/backend:/workspace:/app

WORKDIR /workspace
ARG APP_UID=1000
ARG APP_GID=1000
RUN set -eux; \
    test "${APP_UID}" != "0"; \
    test "${APP_GID}" != "0"; \
    if ! getent group "${APP_GID}" >/dev/null; then \
        groupadd --gid "${APP_GID}" appgroup; \
    fi; \
    useradd --create-home --uid "${APP_UID}" --gid "${APP_GID}" --shell /usr/sbin/nologin appuser; \
    mkdir -p /app/models; \
    chown -R "${APP_UID}:${APP_GID}" /app/models
COPY backend /workspace/backend
RUN pip install --no-cache-dir "/workspace/backend[dev]"
COPY simulator /workspace/simulator
COPY scripts /workspace/scripts
WORKDIR /workspace/backend
USER ${APP_UID}:${APP_GID}
