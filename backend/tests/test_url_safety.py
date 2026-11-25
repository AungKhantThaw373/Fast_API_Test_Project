import httpx
import pytest

from app.services.url_safety import assert_public_url, provider_http_client


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1:11434",
        "http://169.254.169.254/latest/meta-data",
        "http://10.0.0.1/v1",
        "http://[::1]:8080/v1",
        "http://user:pass@api.example.com/v1",
        "https://api.example.com/v1?target=metadata",
        "file:///etc/passwd",
    ],
)
async def test_private_and_unsafe_provider_urls_are_rejected(url):
    with pytest.raises(ValueError):
        await assert_public_url(url)


@pytest.mark.asyncio
async def test_public_url_is_accepted(monkeypatch):
    monkeypatch.setattr("app.services.url_safety._resolve", lambda host, port: ["93.184.216.34"])
    await assert_public_url("https://api.example.com/v1")


@pytest.mark.asyncio
async def test_provider_allowlist_is_enforced(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "PROVIDER_HOST_ALLOWLIST", "api.allowed.test")
    with pytest.raises(ValueError, match="allowlist"):
        await assert_public_url("https://api.example.com/v1")


@pytest.mark.asyncio
async def test_saving_a_private_provider_url_is_rejected(user_client):
    response = await user_client.put(
        "/ai-settings",
        json={
            "provider": "custom",
            "model": "local-model",
            "base_url": "http://169.254.169.254/latest/meta-data",
            "api_key": "test-key",
        },
    )
    assert response.status_code == 422
    assert "private or reserved" in response.json()["detail"]


@pytest.mark.asyncio
async def test_loopback_is_accepted_for_local_ollama_only(user_client):
    accepted = await user_client.put(
        "/ai-settings",
        json={"provider": "ollama", "model": "qwen3:4b-instruct", "base_url": "http://127.0.0.1:11434"},
    )
    assert accepted.status_code == 200

    rejected = await user_client.put(
        "/ai-settings",
        json={
            "provider": "custom",
            "model": "local-model",
            "base_url": "http://127.0.0.1:11434",
            "api_key": "test-key",
        },
    )
    assert rejected.status_code == 422
    assert "private or reserved" in rejected.json()["detail"]


@pytest.mark.asyncio
async def test_private_allowance_still_rejects_metadata_addresses():
    with pytest.raises(ValueError, match="private or reserved"):
        await assert_public_url("http://169.254.169.254/latest/meta-data", allow_private=True)


@pytest.mark.asyncio
async def test_provider_client_does_not_follow_redirects():
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        return httpx.Response(302, headers={"location": "http://127.0.0.1/secret"})

    async with provider_http_client(transport=httpx.MockTransport(handler)) as client:
        response = await client.post("https://public.example/v1/chat")
    assert response.status_code == 302
    assert seen == ["https://public.example/v1/chat"]