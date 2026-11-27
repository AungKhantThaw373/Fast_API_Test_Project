import logging
import re

from conftest import PASSWORD, login, make_test_client, register

from app.security import decode_access_token

NEW_PASSWORD = "a newer quiet password"


def reset_token(caplog) -> str:
    match = re.search(r"http://localhost:3000/reset\?token=([A-Za-z0-9_-]+)", caplog.text)
    assert match, caplog.text
    return match.group(1)


async def test_login_issues_a_complete_verifiable_token(user_client):
    token = user_client.cookies.get("token")
    assert token
    claims = decode_access_token(token)
    for claim in ("sub", "iat", "jti", "iss", "aud", "ver"):
        assert claim in claims
    assert claims["iss"] == "stillroom"
    assert claims["aud"] == "stillroom-api"


async def test_sessions_are_listed_and_one_device_can_be_revoked(client):
    assert (await register(client, "writer", "writer@example.com")).status_code == 201
    assert (await login(client, "writer@example.com")).status_code == 200
    second = make_test_client()
    try:
        assert (await login(second, "writer@example.com")).status_code == 200
        listed = await client.get("/sessions")
        assert listed.status_code == 200
        sessions = listed.json()["sessions"]
        assert len(sessions) == 2
        assert sum(item["current"] for item in sessions) == 1
        other = next(item for item in sessions if not item["current"])

        revoked = await client.delete(f"/sessions/{other['id']}")
        assert revoked.status_code == 200
        assert (await second.get("/me")).status_code == 401
        assert (await client.get("/me")).status_code == 200
    finally:
        await second.aclose()


async def test_a_writer_cannot_revoke_someone_elses_session(client, make_client):
    assert (await register(client, "writer", "writer@example.com")).status_code == 201
    assert (await login(client, "writer@example.com")).status_code == 200
    target = (await client.get("/sessions")).json()["sessions"][0]["id"]
    stranger = await make_client("stranger", "stranger@example.com")
    response = await stranger.delete(f"/sessions/{target}")
    assert response.status_code == 404


async def test_revoke_all_invalidates_every_token(client):
    assert (await register(client, "writer", "writer@example.com")).status_code == 201
    assert (await login(client, "writer@example.com")).status_code == 200
    second = make_test_client()
    try:
        assert (await login(second, "writer@example.com")).status_code == 200
        assert (await client.post("/sessions/revoke-all")).status_code == 200
        assert (await client.get("/me")).status_code == 401
        assert (await second.get("/me")).status_code == 401
    finally:
        await second.aclose()


async def test_forgot_password_logs_a_single_use_link_locally(client, caplog):
    assert (await register(client, "writer", "writer@example.com")).status_code == 201
    with caplog.at_level(logging.WARNING, logger="stillroom.email"):
        response = await client.post("/forgot-password", json={"email": "writer@example.com"})
    assert response.status_code == 202
    assert "reset link has been sent" in response.json()["message"]
    token = reset_token(caplog)

    changed = await client.post(
        "/reset-password", json={"token": token, "new_password": NEW_PASSWORD}
    )
    assert changed.status_code == 200
    assert (await login(client, "writer@example.com")).status_code == 401
    assert (await login(client, "writer@example.com", NEW_PASSWORD)).status_code == 200

    replay = await client.post(
        "/reset-password", json={"token": token, "new_password": "another password entirely"}
    )
    assert replay.status_code == 400


async def test_forgot_password_does_not_reveal_unknown_accounts(client, caplog):
    with caplog.at_level(logging.WARNING, logger="stillroom.email"):
        response = await client.post("/forgot-password", json={"email": "nobody@example.com"})
    assert response.status_code == 202
    assert "nobody@example.com" not in caplog.text


async def test_expired_reset_token_is_rejected(client, caplog, session):
    from datetime import UTC, datetime, timedelta

    from sqlalchemy import update

    from app.models.security_models import PasswordResetToken

    assert (await register(client, "writer", "writer@example.com")).status_code == 201
    with caplog.at_level(logging.WARNING, logger="stillroom.email"):
        assert (await client.post("/forgot-password", json={"email": "writer@example.com"})).status_code == 202
    token = reset_token(caplog)
    import hashlib

    await session.execute(
        update(PasswordResetToken)
        .where(PasswordResetToken.token_hash == hashlib.sha256(token.encode()).hexdigest())
        .values(expires_at=datetime.now(UTC) - timedelta(minutes=1))
    )
    await session.commit()
    response = await client.post(
        "/reset-password", json={"token": token, "new_password": NEW_PASSWORD}
    )
    assert response.status_code == 400


async def test_password_reset_revokes_existing_sessions(client, caplog):
    assert (await register(client, "writer", "writer@example.com")).status_code == 201
    assert (await login(client, "writer@example.com")).status_code == 200
    assert (await client.get("/sessions")).json()["sessions"]
    with caplog.at_level(logging.WARNING, logger="stillroom.email"):
        assert (await client.post("/forgot-password", json={"email": "writer@example.com"})).status_code == 202
    token = reset_token(caplog)
    assert (await client.post(
        "/reset-password", json={"token": token, "new_password": NEW_PASSWORD}
    )).status_code == 200
    assert (await client.get("/me")).status_code == 401


async def test_changing_a_password_requires_the_current_one_and_signs_out(user_client):
    wrong = await user_client.post(
        "/account/password",
        json={"current_password": "not the password", "new_password": NEW_PASSWORD},
    )
    assert wrong.status_code == 400
    changed = await user_client.post(
        "/account/password",
        json={"current_password": PASSWORD, "new_password": NEW_PASSWORD},
    )
    assert changed.status_code == 200
    assert (await user_client.get("/me")).status_code == 401
    assert (await login(user_client, "writer@example.com", PASSWORD)).status_code == 401
    assert (await login(user_client, "writer@example.com", NEW_PASSWORD)).status_code == 200