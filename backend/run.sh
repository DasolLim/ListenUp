#!/usr/bin/env bash
# Start the ListenUp backend (dev mode, auto-reload).
# Loads the repo-root .env so API keys and TRANSCRIPTION_SERVICE apply automatically.
set -euo pipefail
cd "$(dirname "$0")"
if [ -f ../.env ]; then
  set -a
  # shellcheck disable=SC1091
  source ../.env
  set +a
fi
echo "transcription service: ${TRANSCRIPTION_SERVICE:-mock}"
exec .venv/bin/uvicorn app.main:app --reload --port "${BACKEND_PORT:-8000}"
