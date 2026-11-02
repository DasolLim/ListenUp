import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_feedback_recorded_and_logged(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level("INFO", logger="listenup.feedback"):
        response = client.post(
            "/feedback/captions",
            json={
                "session_id": "test-session",
                "rating": "up",
                "final_captions": 5,
                "latency_p50_ms": 120.5,
                "latency_p95_ms": 340.2,
            },
        )
    assert response.status_code == 200
    assert response.json() == {"status": "recorded"}
    assert any(
        "caption_feedback session=test-session rating=up finals=5 p50_ms=120 p95_ms=340"
        in r.message
        for r in caplog.records
    )


def test_feedback_rejects_bad_rating() -> None:
    response = client.post(
        "/feedback/captions",
        json={"session_id": "s", "rating": "meh", "final_captions": 0},
    )
    assert response.status_code == 422
