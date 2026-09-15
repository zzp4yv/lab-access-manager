#!/usr/bin/env bash
set -euo pipefail

mkdir -p "$(dirname "${DATABASE_URL#sqlite:///}")" 2>/dev/null || true
mkdir -p "${UPLOAD_DIR:-/app/data/uploads}"

echo "Iniciando lab-access-manager (ambiente=${ENVIRONMENT:-production}, provisioning_mode=${PROVISIONING_MODE:-dry_run})..."

exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers
