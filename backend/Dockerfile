# ListenUp backend — FastAPI + ECAPA-TDNN, CPU only.
#
# Layer order is deliberate and is most of the value here. Torch is ~200 MB and
# the ECAPA weights ~80 MB; both change almost never, while `app/` changes every
# push. Installing them before the source is copied means a code deploy reuses
# the cached layers instead of re-downloading a machine-learning stack.
# Build for amd64. PyTorch's CPU wheel index carries torch 2.13 for
# manylinux x86_64 but nothing newer than 2.9.1 for aarch64, so a native build
# on Apple silicon cannot satisfy these pins at all. Railway builds amd64
# anyway; locally you need `docker build --platform linux/amd64 .`, which is
# emulated and slow but is the only build that matches production.
FROM python:3.12-slim

# libgomp1 is torch's OpenMP runtime; curl is only for the container healthcheck.
RUN apt-get update \
 && apt-get install -y --no-install-recommends libgomp1 curl \
 && rm -rf /var/lib/apt/lists/*

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    # Read at import time by services/speaker_id/real.py, so it must be an ENV
    # in the image and not merely set during the build step below.
    SPEAKER_MODEL_CACHE=/opt/models/ecapa \
    # SpeechBrain does not copy weights into `savedir` — it writes **symlinks**
    # pointing into the HuggingFace cache. Leaving HF_HOME at its default put
    # the real 80 MB under /root, so `savedir` held 24 KB of links to a
    # directory the app user cannot read, and loading the model at startup died
    # with `Permission denied`. Both paths have to live somewhere the runtime
    # user owns.
    HF_HOME=/opt/models/hf

WORKDIR /srv

# --- Dependency layers, heaviest and most stable first ----------------------
COPY requirements-ml.txt .
# CPU-only wheels. The default PyPI torch pulls the entire CUDA runtime — well
# over a gigabyte of libraries — and speaker ID runs on CPU by constraint
# (CLAUDE.md: "Runs locally, CPU only. No per-call cost."). A GPU image here
# would be pure download and pure storage cost.
RUN pip install --index-url https://download.pytorch.org/whl/cpu \
      --extra-index-url https://pypi.org/simple -r requirements-ml.txt

COPY requirements.txt .
RUN pip install -r requirements.txt

# --- The runtime user, created *before* the model is baked -------------------
# Nothing here needs root, and a container that captures audio for disabled
# users is not the place to make an exception. The user is created early
# because the bake below must run *as* them: a root-owned model cache is
# unreadable at runtime, which is a crash loop rather than a warning.
RUN useradd --create-home --uid 10001 listenup \
 && mkdir -p /opt/models \
 && chown -R listenup:listenup /opt/models /srv
USER listenup

# --- Bake the model into the image ------------------------------------------
# Without this the first request after every deploy waits on an 80 MB download
# from HuggingFace, and a HuggingFace outage becomes a ListenUp outage. The
# source is copied first because the loader lives in it.
COPY --chown=listenup:listenup services ./services
RUN SPEAKER_ID_SERVICE=real python -c "\
from services.speaker_id import get_speaker_embedder; \
get_speaker_embedder().load(); \
print('ECAPA weights cached')"

# --- Application ------------------------------------------------------------
COPY --chown=listenup:listenup app ./app
COPY --chown=listenup:listenup db ./db
COPY --chown=listenup:listenup pyproject.toml .

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
  CMD curl -fsS "http://localhost:${PORT:-8000}/health" || exit 1

# `sh -c` so ${PORT} expands — Railway assigns the port at run time — and
# `exec` so uvicorn *replaces* the shell and becomes PID 1. Without exec, the
# shell holds PID 1, SIGTERM never reaches uvicorn, and a redeploy hard-kills
# live caption sessions instead of draining them. This app makes a point of
# never cutting a session mid-sentence; that promise ends at the process
# boundary unless signals get through.
#
# One worker: the ECAPA model is ~1 GB resident and each worker loads its own
# copy, so scale with instances rather than with workers.
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
