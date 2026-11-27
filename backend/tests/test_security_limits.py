import pytest
from conftest import login, register
from sqlalchemy import func, select

from app.models.security_models import LoginAttempt
from app.rate_limits import TokenBucketLimiter, reset_rate_limits


@pytest.mark.asyncio
async def test_five_failures_lock_the_account(client):
    assert (await register(client, "locked", "locked@example.com")).status_code == 201
    for _ in range(5):
        response = await login(client, "locked@example.com", "wrong password")
        assert response.status_code == 401
    blocked = await login(client, "locked@example.com")
    assert blocked.status_code == 429
    assert blocked.headers["retry-after"] == "900"
    assert "Too many failed" in blocked.json()["detail"]


@pytest.mark.asyncio
async def test_successful_login_clears_failure_counter(client, session):
    assert (await register(client, "clears", "clears@example.com")).status_code == 201
    for _ in range(4):
        assert (await login(client, "clears@example.com", "wrong password")).status_code == 401
    assert (await login(client, "clears@example.com")).status_code == 200
    remaining = await session.scalar(
        select(func.count(LoginAttempt.id)).where(LoginAttempt.success.is_(False))
    )
    assert remaining == 0
    # A full fresh run of four failures still fits under the limit.
    for _ in range(4):
        assert (await login(client, "clears@example.com", "wrong password")).status_code == 401
    assert (await login(client, "clears@example.com")).status_code == 200


@pytest.mark.asyncio
async def test_login_attempts_are_audited(client, session):
    assert (await register(client, "audit", "audit@example.com")).status_code == 201
    await login(client, "audit@example.com", "wrong password")
    await login(client, "audit@example.com")
    rows = (await session.scalars(select(LoginAttempt).order_by(LoginAttempt.created_at))).all()
    # A successful sign-in clears the failure counter but keeps a success row.
    assert [row.success for row in rows] == [True]
    assert all(row.email == "audit@example.com" for row in rows)


@pytest.mark.asyncio
async def test_register_is_limited_per_address(client):
    for index in range(3):
        response = await register(client, f"new{index}", f"new{index}@example.com")
        assert response.status_code == 201
    blocked = await register(client, "new4", "new4@example.com")
    assert blocked.status_code == 429
    assert "Too many accounts" in blocked.json()["detail"]


@pytest.mark.asyncio
async def test_ai_scan_limit_is_per_user(user_client):
    created = await user_client.post("/stories", json={"title": "Limit story"})
    assert created.status_code == 201
    story_id = created.json()["id"]
    for _ in range(10):
        await user_client.post(f"/stories/{story_id}/ask", json={"question": "Who is here?"})
    blocked = await user_client.post(f"/stories/{story_id}/ask", json={"question": "Who is here?"})
    assert blocked.status_code == 429
    assert "AI scan limit" in blocked.json()["detail"]


def test_token_bucket_refills(monkeypatch):
    clock = [1000.0]
    monkeypatch.setattr("app.rate_limits.time.monotonic", lambda: clock[0])
    bucket = TokenBucketLimiter()
    assert bucket.consume("key", 2, 60) is None
    assert bucket.consume("key", 2, 60) is None
    assert bucket.consume("key", 2, 60) == 30
    clock[0] += 30
    assert bucket.consume("key", 2, 60) is None
    reset_rate_limits()