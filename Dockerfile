FROM python:3.11.15-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY pyproject.toml README.md ./
COPY app ./app
COPY data/chunks/pydantic-v2-migration.json ./data/chunks/
COPY data/manifests/pydantic-v2-migration.json ./data/manifests/
COPY data/snapshots/pydantic-v2-migration/migration.md ./data/snapshots/pydantic-v2-migration/

RUN python -m pip install . \
    && mkdir -p /app/var/data \
    && chown -R 10001:10001 /app/var

USER 10001:10001

EXPOSE 8000

CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
