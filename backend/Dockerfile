FROM python:3.12.6-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/workspace/backend:/workspace:/app

WORKDIR /workspace
RUN useradd --create-home --uid 1000 appuser
COPY backend /workspace/backend
RUN pip install --no-cache-dir "/workspace/backend[dev]"
COPY simulator /workspace/simulator
COPY scripts /workspace/scripts
WORKDIR /workspace/backend
USER appuser
