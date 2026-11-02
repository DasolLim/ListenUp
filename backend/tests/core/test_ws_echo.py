from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_ws_echo_roundtrip() -> None:
    with client.websocket_connect("/ws/echo") as ws:
        ws.send_text("hello listenup")
        assert ws.receive_text() == "hello listenup"
        ws.send_text("second message")
        assert ws.receive_text() == "second message"
