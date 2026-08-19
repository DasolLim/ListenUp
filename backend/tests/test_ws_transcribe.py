import json
import wave

import pytest
from fastapi.testclient import TestClient

from app.main import app
from services.assemblyai.mock import FIXTURES_DIR

client = TestClient(app)

CHUNK_BYTES = 16000 * 2 * 200 // 1000  # 200 ms


def wav_chunks() -> list[bytes]:
    with wave.open(str(FIXTURES_DIR / "sample_16k.wav"), "rb") as w:
        pcm = w.readframes(w.getnframes())
    return [pcm[i : i + CHUNK_BYTES] for i in range(0, len(pcm), CHUNK_BYTES)]


def run_session(fixture: str) -> list[dict]:
    messages: list[dict] = []
    with client.websocket_connect("/ws/transcribe") as ws:
        ws.send_text(json.dumps({"sampleRate": 16000, "encoding": "pcm_s16le", "fixture": fixture}))
        assert json.loads(ws.receive_text())["type"] == "ready"
        for chunk in wav_chunks():
            ws.send_bytes(chunk)
        ws.send_text(json.dumps({"type": "stop"}))
        while True:
            message = json.loads(ws.receive_text())
            if message["type"] == "done":
                break
            messages.append(message)
    return messages


def test_mock_roundtrip_ordered_diarized_json() -> None:
    messages = run_session("family")
    assert messages, "expected segments"
    assert all(m["type"] == "segment" for m in messages)
    assert all(
        set(m) == {"type", "speaker", "speakerName", "text", "start", "end", "isFinal", "turnId"}
        for m in messages
    )
    assert all(m["speakerName"] is None for m in messages), "no names outside enhanced mode"
    # interim and final versions of one utterance share a stable turn id
    by_turn: dict[int, list[dict]] = {}
    for m in messages:
        by_turn.setdefault(m["turnId"], []).append(m)
    for turn_messages in by_turn.values():
        assert turn_messages[-1]["isFinal"], "each turn must end with a final"
        assert len({m["turnId"] for m in turn_messages}) == 1
    finals = [m for m in messages if m["isFinal"]]
    # Speaker labels used to be the provider's diarization labels passed
    # through, and this asserted that sequence. They are now decided from the
    # voice, which is the point: one person split across three labels is one
    # speaker. What the transport still owes is that every turn is labelled,
    # that the labels stay inside the cap, and that they are stable — the
    # specific numbering is a property of the audio, and this fixture's audio
    # deliberately does not correspond to its scripted transcript.
    # `test_session_speakers.py` pins the identity rules on real voices.
    labels = [m["speaker"] for m in finals]
    assert all(labels), "every final turn needs a speaker label"
    named = {label for label in labels if label != "Other"}
    assert len(named) <= 4, f"more than four named speakers on screen: {named}"
    ends = [m["end"] for m in messages]
    assert ends == sorted(ends)


def test_speaker_labels_stay_inside_the_cap() -> None:
    """Seven diarization labels must never produce more than four named
    speakers plus "Other" (INTRODUCTION §5.8).

    This no longer asserts a fixed sequence: voice clustering folds labels that
    sound like the same person, so how many distinct speakers appear depends on
    the audio. The cap is the invariant. `test_session_speakers.py` covers the
    folding itself, where the fixtures are real voices.
    """
    finals = [m for m in run_session("crowd") if m["isFinal"]]
    labels = [m["speaker"] for m in finals]
    assert len(labels) == 7, "every spoken turn should still be captioned"
    named = {label for label in labels if label != "Other"}
    # At most four *displayed at once*. Numbers are never recycled, so a session
    # with folds can legitimately show "Speaker 5" while only four are live —
    # the invariant is the count, not the highest number.
    assert len(named) <= 4, f"more than four named speakers: {named}"


def test_bad_sample_rate_gets_clear_error() -> None:
    with client.websocket_connect("/ws/transcribe") as ws:
        ws.send_text(json.dumps({"sampleRate": 44100, "encoding": "pcm_s16le"}))
        message = json.loads(ws.receive_text())
        assert message["type"] == "error"
        assert "16000 Hz mono pcm_s16le" in message["message"]


def test_abrupt_disconnect_logs_clean_teardown(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level("INFO", logger="listenup.ws.transcribe"):
        with client.websocket_connect("/ws/transcribe") as ws:
            ws.send_text(json.dumps({"sampleRate": 16000, "encoding": "pcm_s16le"}))
            assert json.loads(ws.receive_text())["type"] == "ready"
            for chunk in wav_chunks()[:5]:
                ws.send_bytes(chunk)
            # leave the context without stop → abrupt close

    # TestClient cancels the app task tree on context exit, so the server's
    # finally-block log is unobservable here; full teardown (transcribe_end,
    # no leaked tasks) is verified against live uvicorn in the step gate.
    assert any("transcribe_disconnect" in r.message for r in caplog.records)
