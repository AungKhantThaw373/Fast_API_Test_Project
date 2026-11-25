import pytest
from conftest import CSRF_TOKEN, PASSWORD, make_test_client
from httpx import ASGITransport, AsyncClient

from app.app import app


@pytest.mark.asyncio
async def test_safe_request_issues_a_readable_csrf_cookie():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as raw:
        response = await raw.get("/health")
    assert response.status_code == 200
    cookie = response.headers.get("set-cookie", "")
    assert "csrf=" in cookie
    assert "HttpOnly" not in cookie
    assert "SameSite=Lax" in cookie


@pytest.mark.asyncio
async def test_cross_origin_post_is_rejected(client):
    response = await client.post(
        "/register",
        json={"username": "cross", "email": "cross@example.com", "password": PASSWORD},
        headers={"Origin": "https://evil.example"},
    )
    assert response.status_code == 403
    assert "different site" in response.json()["detail"]


@pytest.mark.asyncio
async def test_cross_site_fetch_metadata_is_rejected(client):
    response = await client.post(
        "/register",
        json={"username": "site", "email": "site@example.com", "password": PASSWORD},
        headers={"Sec-Fetch-Site": "cross-site"},
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_same_origin_post_without_token_is_rejected():
    async with make_test_client() as client:
        response = await client.post(
            "/register",
            json={"username": "noheader", "email": "noheader@example.com", "password": PASSWORD},
            headers={"Origin": "http://test", "X-CSRF-Token": ""},
        )
    assert response.status_code == 403
    assert "Missing security token" in response.json()["detail"]


@pytest.mark.asyncio
async def test_same_origin_post_with_matching_token_succeeds(client):
    response = await client.post(
        "/register",
        json={"username": "same", "email": "same@example.com", "password": PASSWORD},
        headers={"Origin": "http://test", "X-CSRF-Token": CSRF_TOKEN},
    )
    assert response.status_code == 201


@pytest.mark.asyncio
async def test_mismatched_token_is_rejected(client):
    response = await client.post(
        "/register",
        json={"username": "mismatch", "email": "mismatch@example.com", "password": PASSWORD},
        headers={"X-CSRF-Token": "not-the-cookie"},
    )
    assert response.status_code == 403