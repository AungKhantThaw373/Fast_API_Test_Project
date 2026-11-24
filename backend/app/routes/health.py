"""Liveness and readiness.

``/health`` is process-only and cheap. ``/ready`` checks the database, pgvector,
the schema revision, Ollama, and a fresh worker heartbeat; it answers 503 with a
per-dependency report when something is missing.
"""

from fastapi import APIRouter, Response, status

from app.db import async_session
from app.services.health import readiness_report

router = APIRouter(tags=["system"])


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/ready")
async def ready(response: Response) -> dict[str, object]:
    async with async_session() as session:
        is_ready, report = await readiness_report(session)
    if not is_ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    report["status"] = "ready" if is_ready else "not_ready"
    return report
