# syntax=docker/dockerfile:1
FROM python:3.11-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Dependências de sistema mínimas (paramiko precisa de libffi/openssl,
# já presentes na imagem slim via libssl/libffi runtime; build-essential
# só é necessário se alguma dependência precisar compilar).
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        libffi-dev \
        curl \
    && rm -rf /var/lib/apt/lists/*

# Instala dependências Python primeiro (aproveita cache de camadas).
COPY backend/requirements.txt /app/backend/requirements.txt
RUN pip install --no-cache-dir -r /app/backend/requirements.txt

# Copia o restante do projeto preservando a estrutura de pastas
# (backend/ e frontend/ lado a lado), pois app/config.py calcula o
# caminho do frontend estático de forma relativa a este layout.
COPY backend /app/backend
COPY frontend /app/frontend
COPY scripts/entrypoint.sh /app/entrypoint.sh

RUN chmod +x /app/entrypoint.sh \
    && mkdir -p /app/backend/data/uploads /app/secrets \
    && useradd --create-home --shell /bin/bash appuser \
    && chown -R appuser:appuser /app

WORKDIR /app/backend
USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -fsS http://localhost:8000/api/health || exit 1

ENTRYPOINT ["/app/entrypoint.sh"]
