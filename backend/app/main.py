import os

import sentry_sdk
from fastapi import FastAPI

# No-op without a DSN: sentry_sdk.init is only called when SENTRY_DSN is set.
if os.environ.get("SENTRY_DSN"):
    sentry_sdk.init(
        dsn=os.environ["SENTRY_DSN"],
        traces_sample_rate=0.1,
        send_default_pii=False,
    )

app = FastAPI(title="ListenUp API")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
