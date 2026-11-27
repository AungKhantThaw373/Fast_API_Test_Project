import logging
from datetime import UTC, datetime

from sqlalchemy import text

from app.config import settings


async def test_diagnostics_reports_database_jobs_and_model(user_client):
    response = await user_client.get("/system/diagnostics")
    assert response.status_code == 200
    body = response.json()
    assert body["database"] == "ok"
    assert body["database_size_bytes"] > 0
    assert set(body["jobs"]) == {"queued", "running", "succeeded", "failed", "dead"}
    assert body["ollama"] in {"ok", "unreachable"} or body["ollama"].startswith(("error", "missing"))
    assert "api_key" not in str(body).lower()


async def test_diagnostics_finds_the_newest_backup(user_client, tmp_path, monkeypatch):
    older = tmp_path / "stillroom-older.dump"
    older.write_bytes(b"old")
    newer = tmp_path / "stillroom-newer.dump"
    newer.write_bytes(b"newer backup")
    monkeypatch.setattr(settings, "BACKUP_DIR", str(tmp_path))

    body = (await user_client.get("/system/diagnostics")).json()
    assert body["last_backup"]["filename"] == "stillroom-newer.dump"
    assert body["last_backup"]["size_bytes"] == 12
    datetime.fromisoformat(body["last_backup"]["modified_at"]).astimezone(UTC)


async def test_diagnostics_requires_authentication(client):
    assert (await client.get("/system/diagnostics")).status_code == 401


async def test_slow_queries_are_logged_without_parameters(session, caplog, monkeypatch):
    monkeypatch.setattr(settings, "SLOW_QUERY_MS", 1)
    with caplog.at_level(logging.WARNING, logger="stillroom.slow_query"):
        await session.execute(text("SELECT pg_sleep(:seconds)"), {"seconds": 0.01})

    messages = [record.getMessage() for record in caplog.records if record.name == "stillroom.slow_query"]
    assert any("slow_query duration_ms=" in message for message in messages)
    assert any("SELECT pg_sleep" in message for message in messages)
    # Parameters stay out of logs even when they are harmless.
    assert all("0.01" not in message for message in messages)