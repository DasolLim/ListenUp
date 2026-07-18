"""Load the repo-root .env into os.environ WITHOUT overriding variables the
shell already set — `TRANSCRIPTION_SERVICE=mock ./run.sh` must win over .env."""

import os
from pathlib import Path

ENV_PATH = Path(__file__).resolve().parents[2] / ".env"


def load_env() -> None:
    if not ENV_PATH.is_file():
        return
    for line in ENV_PATH.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))
