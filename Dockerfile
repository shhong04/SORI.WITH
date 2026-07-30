# syntax=docker/dockerfile:1
FROM python:3.13-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    SORI_WITH_ENVIRONMENT=production \
    SORI_WITH_ALLOW_PATH_ANALYZE=false \
    SORI_WITH_MAX_UPLOAD_BYTES=20971520 \
    SORI_WITH_CORS_ORIGINS=*

RUN apt-get update && apt-get install -y --no-install-recommends \
      libsndfile1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

COPY pyproject.toml ./
COPY config ./config
COPY sori_with ./sori_with
COPY web ./web
COPY data/.gitkeep ./data/.gitkeep

RUN mkdir -p data/uploads data/reports \
    && useradd --create-home --uid 10001 appuser \
    && chown -R appuser:appuser /app

USER appuser

EXPOSE 8000

# Render/Railway inject PORT
CMD ["sh", "-c", "uvicorn sori_with.api.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
