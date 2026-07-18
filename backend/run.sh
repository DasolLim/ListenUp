#!/usr/bin/env bash
# Start the ListenUp backend (dev mode, auto-reload).
# Root .env is loaded inside the app (app/env.py) with shell-env precedence,
# so overrides like `TRANSCRIPTION_SERVICE=mock ./run.sh` work as expected.
set -euo pipefail
cd "$(dirname "$0")"
ENV_TS=$(grep -E '^TRANSCRIPTION_SERVICE=' ../.env 2>/dev/null | cut -d= -f2 || true)
ENV_PORT=$(grep -E '^BACKEND_PORT=' ../.env 2>/dev/null | cut -d= -f2 || true)
echo "transcription service: ${TRANSCRIPTION_SERVICE:-${ENV_TS:-mock}}"
exec .venv/bin/uvicorn app.main:app --reload --port "${BACKEND_PORT:-${ENV_PORT:-8000}}"
