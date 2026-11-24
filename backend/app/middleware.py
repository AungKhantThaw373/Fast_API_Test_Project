"""Request ids: one id per request, in logs, headers, and error bodies.

A writer reports "saving failed"; the status UI shows an id; the id finds the
exact log lines for that request. The id also travels to the job payload logs, so
an index job can be traced back to the save that queued it.
"""

from __future__ import annotations

import logging
import time
from contextvars import ContextVar
from uuid import uuid4

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

from app.logging_config import fields, get_logger

REQUEST_ID_HEADER = "X-Request-ID"

_request_id: ContextVar[str] = ContextVar("request_id", default="-")
logger = get_logger("api")


def current_request_id() -> str:
    return _request_id.get()


def set_request_id(value: str) -> None:
    _request_id.set(value)


class RequestIdFilter(logging.Filter):
    """Attach the active request id to every log record."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = _request_id.get()
        return True


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Assign a request id, time the request, and log one line per request."""

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        incoming = request.headers.get(REQUEST_ID_HEADER, "").strip()
        request_id = incoming[:64] if incoming else uuid4().hex[:12]
        token = _request_id.set(request_id)
        started = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            logger.exception(
                "request failed  %s",
                fields(
                    request_id=request_id,
                    method=request.method,
                    path=request.url.path,
                    duration=f"{(time.perf_counter() - started) * 1000:.0f}ms",
                ),
            )
            raise
        finally:
            _request_id.reset(token)
        response.headers[REQUEST_ID_HEADER] = request_id
        logger.info(
            "request         %s",
            fields(
                request_id=request_id,
                method=request.method,
                path=request.url.path,
                status=response.status_code,
                duration=f"{(time.perf_counter() - started) * 1000:.0f}ms",
            ),
        )
        return response
