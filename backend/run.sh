#!/usr/bin/env bash
# Start the ListenUp backend (dev mode, auto-reload).
set -euo pipefail
cd "$(dirname "$0")"
exec .venv/bin/uvicorn app.main:app --reload --port "${BACKEND_PORT:-8000}"
