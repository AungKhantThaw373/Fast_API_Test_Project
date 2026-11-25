"""Ollama structured output: schema validation, retry, and settings."""

import json

import pytest

from app.services.ai_service import _ollama_structured
from app.services.ai_settings import AIConfig


SCHEMA = {
    "type": "object",
    "properties": {"name": {"type": "string"}, "confidence": {"type": "integer"}},
    "required": ["name", "confidence"],
    "additionalProperties": False,
}


class FakeResponse:
    def __init__(self, payload, status=200):
        self._payload = payload
        self.status_code = status
        self.is_error = status >= 400

    def json(self):
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload


class FakeClient:
    responses: list[FakeResponse] = []
    calls: list[dict] = []

    def __init__(self, **kwargs):
        self.kwargs = kwargs

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def post(self, url, **kwargs):
        FakeClient.calls.append({"url": url, **kwargs})
        return FakeClient.responses.pop(0)


def ollama_config() -> AIConfig:
    return AIConfig(
        provider="ollama",
        model="qwen3:4b-instruct",
        api_key="",
        base_url="http://127.0.0.1:11434",
        protocol="ollama",
    )


async def call(monkeypatch, responses):
    FakeClient.responses = list(responses)
    FakeClient.calls = []
    monkeypatch.setattr("app.services.ai_service.httpx.AsyncClient", FakeClient)
    return await _ollama_structured(
        ollama_config(),
        "system",
        "user",
        SCHEMA,
        purpose="extraction",
        schema_name="entries",
        call_id="test",
        started=0.0,
        timeout_seconds=5,
    )


async def test_ollama_returns_schema_valid_json(monkeypatch):
    result = await call(monkeypatch, [FakeResponse({"message": {"content": '{"name": "Mira", "confidence": 90}'}})])
    assert result == {"name": "Mira", "confidence": 90}
    sent = FakeClient.calls[0]
    assert sent["url"].endswith("/api/chat")
    assert sent["json"]["format"] == SCHEMA
    assert sent["json"]["stream"] is False
    assert sent["json"]["options"]["num_ctx"] > 0


async def test_ollama_retries_invalid_json_once(monkeypatch):
    result = await call(
        monkeypatch,
        [
            FakeResponse({"message": {"content": "not json"}}),
            FakeResponse({"message": {"content": '{"name": "Mira", "confidence": 90}'}}),
        ],
    )
    assert result["name"] == "Mira"
    assert len(FakeClient.calls) == 2


async def test_ollama_retries_schema_mismatch_once(monkeypatch):
    with pytest.raises(RuntimeError, match="did not match"):
        await call(
            monkeypatch,
            [
                FakeResponse({"message": {"content": '{"name": "Mira"}'}}),
                FakeResponse({"message": {"content": '{"name": "Mira", "extra": true}'}}),
            ],
        )
    assert len(FakeClient.calls) == 2


async def test_ollama_does_not_retry_http_error(monkeypatch):
    from app.services.ai_service import AIProviderHTTPError

    with pytest.raises(AIProviderHTTPError):
        await call(monkeypatch, [FakeResponse({"error": "model not found"}, status=404)])
    assert len(FakeClient.calls) == 1


async def test_ai_settings_accept_ollama_without_key(user_client):
    providers = await user_client.get("/ai-providers")
    assert providers.status_code == 200
    assert any(item["id"] == "ollama" for item in providers.json()["providers"])

    saved = await user_client.put(
        "/ai-settings",
        json={"provider": "ollama", "model": "qwen3:4b-instruct"},
    )
    assert saved.status_code == 200, saved.text
    body = saved.json()
    assert body["provider"] == "ollama"
    assert body["model"] == "qwen3:4b-instruct"
    assert body["base_url"].startswith("http://127.0.0.1:11434")

    fetched = await user_client.get("/ai-settings")
    assert fetched.json()["provider"] == "ollama"


async def test_ai_settings_view_without_key_defaults_to_ollama(client):
    from app.config import settings

    original = settings.OPENROUTER_API_KEY
    settings.OPENROUTER_API_KEY = None
    try:
        await client.post("/register", json={"username": "local", "email": "local@example.com", "password": "correct horse battery"})
        await client.post("/token", data={"username": "local@example.com", "password": "correct horse battery"})
        response = await client.get("/ai-settings")
        assert response.status_code == 200
        assert response.json()["provider"] == "ollama"
        assert response.json()["using_server_default"] is True
    finally:
        settings.OPENROUTER_API_KEY = original
