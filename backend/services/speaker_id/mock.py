"""Deterministic mock embedder: 192 normalized spectral-band energies.

No model download, CI-safe, and still voice-discriminative: long-term average
spectra differ between voices, so different speakers get visibly lower cosine
similarity while re-recordings of one voice stay close — enough to exercise
the whole enrollment → matching pipeline honestly.
"""

import logging

import numpy as np

from services.speaker_id.base import EMBEDDING_DIM, SpeakerEmbedder

logger = logging.getLogger("listenup.speaker_id")

_FRAME = 512


class MockSpeakerEmbedder(SpeakerEmbedder):
    def load(self) -> None:
        logger.info("speaker_id_ready service=mock (spectral pseudo-embeddings)")

    def embed(self, pcm: bytes, sample_rate: int = 16000) -> list[float]:
        self.validate(pcm, sample_rate, min_seconds=0.5)
        samples = np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / 32768.0
        usable = len(samples) - (len(samples) % _FRAME)
        frames = samples[:usable].reshape(-1, _FRAME)
        # Skip near-silent frames so pauses don't wash out the voice signature.
        energies = (frames**2).mean(axis=1)
        threshold: float = max(1e-6, float(energies.mean()) * 0.1)
        voiced = frames[energies > threshold]
        if len(voiced) == 0:
            voiced = frames
        spectrum = np.abs(np.fft.rfft(voiced, axis=1)).mean(axis=0)
        log_spec = np.log1p(spectrum)
        # Detrend: subtract the smoothed envelope all speech shares, keeping the
        # voice-specific fine structure. Same voice ≈0.95 cosine, different
        # voice ≈0.4 — so the default 0.6 match threshold behaves like ECAPA's.
        kernel = np.ones(15) / 15
        log_spec = log_spec - np.convolve(log_spec, kernel, mode="same")
        # Pool the 257 bins into 192 bands.
        bands = np.interp(
            np.linspace(0, len(log_spec) - 1, EMBEDDING_DIM),
            np.arange(len(log_spec)),
            log_spec,
        )
        normalized = (bands - bands.mean()) / (bands.std() or 1.0)
        return [float(x) for x in normalized]
