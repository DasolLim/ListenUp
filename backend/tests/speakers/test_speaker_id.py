import wave
from pathlib import Path

import pytest

from services.assemblyai.base import AudioFormatError
from services.speaker_id import EMBEDDING_DIM, cosine_similarity, get_speaker_embedder
from services.speaker_id.mock import MockSpeakerEmbedder

FIXTURES = Path(__file__).parents[2] / "services" / "speaker_id" / "fixtures"


def pcm(name: str) -> bytes:
    with wave.open(str(FIXTURES / f"{name}.wav"), "rb") as w:
        return w.readframes(w.getnframes())


@pytest.fixture(scope="module")
def embedder() -> MockSpeakerEmbedder:
    service = MockSpeakerEmbedder()
    service.load()
    return service


def test_dimension_and_determinism(embedder: MockSpeakerEmbedder) -> None:
    first = embedder.embed(pcm("sam1"))
    second = embedder.embed(pcm("sam1"))
    assert len(first) == EMBEDDING_DIM
    assert cosine_similarity(first, second) > 0.999  # same clip → near-identical


def test_same_voice_close_different_voice_far(embedder: MockSpeakerEmbedder) -> None:
    sam1 = embedder.embed(pcm("sam1"))
    sam2 = embedder.embed(pcm("sam2"))  # same voice, different sentence
    dan1 = embedder.embed(pcm("dan1"))  # different voice, same sentence

    same_voice = cosine_similarity(sam1, sam2)
    cross_voice = cosine_similarity(sam1, dan1)
    assert same_voice > cross_voice, f"same={same_voice:.3f} cross={cross_voice:.3f}"
    # The 0.6 default match threshold must separate these cleanly.
    assert same_voice > 0.75, f"same-voice too low: {same_voice:.3f}"
    assert cross_voice < 0.55, f"cross-voice too high: {cross_voice:.3f}"


def test_rejects_wrong_sample_rate(embedder: MockSpeakerEmbedder) -> None:
    with pytest.raises(AudioFormatError):
        embedder.embed(pcm("sam1"), sample_rate=44100)


def test_rejects_too_short_audio(embedder: MockSpeakerEmbedder) -> None:
    with pytest.raises(ValueError, match="too short"):
        embedder.embed(pcm("sam1")[: 16000 // 2], sample_rate=16000)  # ~0.25 s


def test_factory_defaults_to_mock(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SPEAKER_ID_SERVICE", raising=False)
    get_speaker_embedder.cache_clear()
    assert isinstance(get_speaker_embedder(), MockSpeakerEmbedder)
    get_speaker_embedder.cache_clear()
