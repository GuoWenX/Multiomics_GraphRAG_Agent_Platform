from __future__ import annotations

import hashlib
import hmac

from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.main import app
from app.services import fastagi_service
from app.services.fastagi_service import calculate_signature


client = TestClient(app)


def test_calculate_signature_matches_fastagi_client_algorithm() -> None:
    app_id = "app-1"
    secret_key = "secret"
    timestamp = "1700000000000"

    expected = hmac.new(secret_key.encode(), f"{app_id}{timestamp}".encode(), hashlib.sha256).hexdigest()

    assert calculate_signature(app_id, secret_key, timestamp) == expected


def test_agent_chat_aggregates_streaming_request(monkeypatch) -> None:
    captured: dict = {}

    monkeypatch.setenv("MOGAP_FASTAGI_BASE_URL", "https://fastagi.example.com")
    monkeypatch.setenv("MOGAP_FASTAGI_CHAT_ENDPOINT", "/api/openapi/chat/chat-messages")
    monkeypatch.setenv("MOGAP_FASTAGI_APP_ID", "app-id")
    monkeypatch.setenv("MOGAP_FASTAGI_SECRET_KEY", "secret-key")
    monkeypatch.setenv("MOGAP_FASTAGI_AGENT_ID", "agent-id")
    monkeypatch.setenv("MOGAP_FASTAGI_APP_USER", "nfyy")
    monkeypatch.setenv("MOGAP_FASTAGI_PROVIDER", "credentials")
    get_settings.cache_clear()
    monkeypatch.setattr(fastagi_service.time, "time", lambda: 1700000000.0)

    class Response:
        ok = True
        status_code = 200
        text = ""

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

        @staticmethod
        def iter_lines(decode_unicode: bool = False):
            lines = [
                'data: {"event":"message","task_id":"task-1","message_id":"message-1","conversation_id":"conversation-1","answer":"o","created_at":1700000000}',
                "",
                'data: {"event":"message","task_id":"task-1","message_id":"message-1","conversation_id":"conversation-1","answer":"k","created_at":1700000000}',
                "",
                'data: {"event":"message_end","task_id":"task-1","message_id":"message-1","conversation_id":"conversation-1","created_at":1700000000}',
                "",
            ]
            return iter(lines)

    def fake_post(url, headers, json, timeout, **kwargs):
        captured.update(
            {
                "url": url,
                "headers": headers,
                "json": json,
                "timeout": timeout,
                "kwargs": kwargs,
            }
        )
        return Response()

    monkeypatch.setattr(fastagi_service.requests, "post", fake_post)

    try:
        response = client.post(
            "/api/v1/agent/chat",
            json={
                "query": "SMPD3 有什么功能？",
                "conversation_id": "conversation-0",
                "parent_message_id": "message-0",
            },
        )
    finally:
        get_settings.cache_clear()

    assert response.status_code == 200
    assert response.json()["answer"] == "ok"
    assert captured["url"] == "https://fastagi.example.com/api/openapi/chat/chat-messages"
    assert captured["json"]["agent_id"] == "agent-id"
    assert captured["json"]["response_mode"] == "streaming"
    assert captured["json"]["conversation_id"] == "conversation-0"
    assert captured["json"]["parent_message_id"] == "message-0"
    assert captured["kwargs"]["stream"] is True
    assert captured["headers"]["app_id"] == "app-id"
    assert captured["headers"]["app_user"] == "nfyy"
    assert captured["headers"]["provider"] == "credentials"
    assert captured["headers"]["timestamp"] == "1700000000000"
    assert captured["headers"]["signature"] == calculate_signature("app-id", "secret-key", "1700000000000")
