FROM python:3.12.13-slim-bookworm@sha256:4766d8b510c428e595d74b9cc5bbb2fae8e26316fffb4adc89908d79aacd58a2

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
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
COPY backend/requirements.lock /workspace/backend/requirements.lock
RUN python -m pip install --no-cache-dir --require-hashes -r /workspace/backend/requirements.lock
COPY backend/build-requirements.lock /workspace/backend/build-requirements.lock
RUN python -m pip install --no-cache-dir --require-hashes -r /workspace/backend/build-requirements.lock
COPY backend /workspace/backend
RUN python -m pip install --no-cache-dir --no-build-isolation --no-deps /workspace/backend; \
    python -m pip uninstall -y setuptools
COPY simulator /workspace/simulator
COPY scripts /workspace/scripts
WORKDIR /workspace/backend
USER ${APP_UID}:${APP_GID}
