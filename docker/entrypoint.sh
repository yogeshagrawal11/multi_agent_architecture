#!/usr/bin/env bash
# Author: Yogesh Agrawal
# Container entrypoint: prepare data dir, init+seed SQLite, optionally bootstrap
# Postgres for Langfuse, then hand off to supervisord (PID 1 process manager).
set -euo pipefail

DATA_DIR="${DATA_DIR:-/data}"
mkdir -p "$DATA_DIR"

echo "[entrypoint] Initializing mock bank SQLite database..."
python -m mock_bank.seed || echo "[entrypoint] WARN: seed step failed (continuing)"

echo "[entrypoint] Initializing session store..."
python -c "from app.session.store import init_db; init_db()" || \
    echo "[entrypoint] WARN: session init failed (continuing)"

# ---- Observability ----
# Langfuse is optional and disabled by default (LANGFUSE_ENABLED=false). The app
# emits traces via the Langfuse SDK only when enabled + configured to point at a
# separately-run Langfuse server. Nothing to bootstrap here.
if [ "${LANGFUSE_ENABLED:-false}" = "true" ]; then
    echo "[entrypoint] Langfuse enabled: expecting external Langfuse at ${LANGFUSE_HOST:-unset}"
else
    echo "[entrypoint] Langfuse disabled (default)."
fi

echo "[entrypoint] Starting supervisord..."
exec /usr/bin/supervisord -c /etc/supervisor/conf.d/app.conf
