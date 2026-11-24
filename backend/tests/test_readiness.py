"""Request ids and the readiness probe."""

from app.services import health
from app.services import jobs as jobs_service


async def test_request_id_is_generated_and_echoed(client):
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.headers["x-request-id"]


async def test_incoming_request_id_is_preserved(client):
    response = await client.get("/health", headers={"X-Request-ID": "abc123"})
    assert response.headers["x-request-id"] == "abc123"


async def test_error_bodies_carry_the_request_id(client):
    response = await client.get("/stories", headers={"X-Request-ID": "trace-me"})
    assert response.status_code == 401
    body = response.json()
    assert body["request_id"] == "trace-me"
    assert body["detail"]


async def test_validation_errors_carry_the_request_id(client):
    response = await client.post("/register", json={})
    assert response.status_code == 422
    body = response.json()
    assert body["request_id"]
    assert body["detail"]


async def test_ready_reports_each_dependency(client, session, monkeypatch):
    async def local_ollama() -> str:
        return "ok"

    monkeypatch.setattr(health, "check_ollama", local_ollama)

    # No worker has ever heartbeated in the test database.
    not_ready = await client.get("/ready")
    assert not_ready.status_code == 503
    body = not_ready.json()
    assert body["status"] == "not_ready"
    assert body["database"] == "ok"
    assert body["pgvector"].startswith("ok")
    assert body["schema"] == "ok"
    assert body["worker"] == "offline"

    await jobs_service.heartbeat(session, "worker-test")
    ready = await client.get("/ready")
    assert ready.status_code == 200
    assert ready.json()["status"] == "ready"
    assert ready.json()["worker"] == "running"


async def test_health_stays_cheap(client):
    """`/health` must not touch the database or a provider."""
    from sqlalchemy import event

    from app.db import engine

    statements: list[str] = []

    def record(_conn, _cursor, statement, _parameters, _context, _executemany):
        statements.append(statement)

    event.listen(engine.sync_engine, "before_cursor_execute", record)
    try:
        assert (await client.get("/health")).status_code == 200
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", record)
    assert statements == []
