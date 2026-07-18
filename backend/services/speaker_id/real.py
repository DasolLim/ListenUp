"""Real ECAPA-TDNN embedder (speechbrain/spkrec-ecapa-voxceleb), CPU-only.

Model weights (~80 MB) download once into MODEL_CACHE_DIR and are reused.
Requires backend/requirements-ml.txt (torch, torchaudio, speechbrain) — kept
out of the CI requirements so pipelines stay light.
"""

import logging
import os
from pathlib import Path

import numpy as np

from services.speaker_id.base import SpeakerEmbedder

logger = logging.getLogger("listenup.speaker_id")

MODEL_SOURCE = "speechbrain/spkrec-ecapa-voxceleb"
MODEL_CACHE_DIR = Path(
    os.environ.get("SPEAKER_MODEL_CACHE", Path.home() / ".cache" / "listenup" / "ecapa")
)


class EcapaSpeakerEmbedder(SpeakerEmbedder):
    def __init__(self) -> None:
        self._model = None

    def load(self) -> None:
        if self._model is not None:
            return
        try:
            import torch  # noqa: F401
            from speechbrain.inference.speaker import EncoderClassifier
        except ImportError as exc:
            raise RuntimeError(
                "ECAPA-TDNN needs the ML extras: "
                "backend/.venv/bin/pip install -r backend/requirements-ml.txt"
            ) from exc
        try:
            self._model = EncoderClassifier.from_hparams(
                source=MODEL_SOURCE,
                savedir=str(MODEL_CACHE_DIR),
                run_opts={"device": "cpu"},
            )
        except Exception as exc:
            raise RuntimeError(
                f"Failed to load {MODEL_SOURCE} (first run downloads ~80 MB — check network "
                f"and that {MODEL_CACHE_DIR} is writable): {exc}"
            ) from exc
        logger.info("speaker_id_ready service=ecapa cache=%s", MODEL_CACHE_DIR)

    def embed(self, pcm: bytes, sample_rate: int = 16000) -> list[float]:
        import torch

        if self._model is None:
            self.load()
        assert self._model is not None
        self.validate(pcm, sample_rate, min_seconds=0.5)
        samples = np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / 32768.0
        with torch.no_grad():
            embedding = self._model.encode_batch(torch.from_numpy(samples).unsqueeze(0))
        return [float(x) for x in embedding.squeeze().tolist()]
