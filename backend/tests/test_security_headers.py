import pytest
from conftest import login, make_test_client, register
from httpx import ASGITransport, AsyncClient

from app.app import app
from app.config import settings


@pytest.mark.asyncio
async def test_baseline_security_headers(client):
    response = await client.get("/health")
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["referrer-policy"] == "strict-origin-when-cross-origin"
    assert response.headers["permissions-policy"] == "camera=(), microphone=(), geolocation=()"
    assert response.headers["x-frame-options"] == "DENY"
    assert "content-security-policy" not in response.headers


@pytest.mark.asyncio
async def test_production_csp_and_hsts(monkeypatch):
    monkeypatch.setattr(settings, "APP_ENV", "production")
    monkeypatch.setattr(settings, "COOKIE_SECURE", True)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="https://test") as secure:
        response = await secure.get("/health")
    assert response.status_code == 200
    assert "frame-ancestors 'none'" in response.headers["content-security-policy"]
    assert response.headers["strict-transport-security"] == "max-age=31536000; includeSubDomains"


@pytest.mark.asyncio
async def test_hsts_is_not_sent_over_plain_http(monkeypatch):
    monkeypatch.setattr(settings, "APP_ENV", "production")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as plain:
        response = await plain.get("/health")
    assert "strict-transport-security" not in response.headers


@pytest.mark.asyncio
async def test_production_auth_cookie_uses_host_prefix(monkeypatch):
    async with make_test_client() as client:
        assert (await register(client, "secure", "secure@example.com")).status_code == 201
        monkeypatch.setattr(settings, "APP_ENV", "production")
        monkeypatch.setattr(settings, "COOKIE_SECURE", True)
        response = await login(client, "secure@example.com")
    assert response.status_code == 200
    cookie = response.headers.get("set-cookie", "")
    assert cookie.startswith("__Host-token=")
    for flag in ("Secure", "HttpOnly", "SameSite=lax", "Path=/"):
        assert flag in cookie
    assert "Domain=" not in cookie