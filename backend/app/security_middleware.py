"""Origin checks and a double-submit CSRF token for cookie-authenticated writes."""

from __future__ import annotations

import hmac
import secrets
from http.cookies import SimpleCookie

from fastapi.responses import JSONResponse
from starlette.datastructures import Headers, MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.config import settings
from app.middleware import current_request_id

UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
CSRF_COOKIE = "csrf"
CSRF_HEADER = "x-csrf-token"


def _cookie_value(header: str | None, name: str) -> str | None:
    if not header:
        return None
    try:
        jar = SimpleCookie()
        jar.load(header)
    except Exception:
        return None
    morsel = jar.get(name)
    return morsel.value if morsel else None


def _csrf_cookie(token: str) -> str:
    parts = [f"{CSRF_COOKIE}={token}", "Path=/", "SameSite=Lax"]
    if settings.COOKIE_SECURE:
        parts.append("Secure")
    return "; ".join(parts)


class SecurityMiddleware:
    """Reject cross-site writes and require a header matching the csrf cookie.

    A safe request without a token gets one. The cookie is readable by the
    app so the API client can echo it; the auth cookie stays HttpOnly.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = Headers(scope=scope)
        method = scope["method"].upper()
        if method in UNSAFE_METHODS:
            denial = self._deny(headers, scope)
            if denial is not None:
                await denial(scope, receive, send)
                return
            await self.app(scope, receive, send)
            return

        existing = _cookie_value(headers.get("cookie"), CSRF_COOKIE)
        if existing:
            await self.app(scope, receive, send)
            return

        token = secrets.token_urlsafe(32)

        async def send_with_cookie(message: Message) -> None:
            if message["type"] == "http.response.start":
                response_headers = MutableHeaders(scope=message)
                response_headers.append("set-cookie", _csrf_cookie(token))
            await send(message)

        await self.app(scope, receive, send_with_cookie)

    def _deny(self, headers: Headers, scope: Scope) -> JSONResponse | None:
        origin = headers.get("origin")
        if origin:
            own_origin = f"{scope.get('scheme', 'http')}://{headers.get('host', '')}"
            allowed = {origin.rstrip("/") for origin in settings.frontend_origins}
            allowed.add(own_origin.rstrip("/"))
            if origin.rstrip("/") not in allowed:
                return self._forbidden("That request came from a different site.")

        if headers.get("sec-fetch-site", "").lower() == "cross-site":
            return self._forbidden("Cross-site requests are not allowed.")

        cookie_token = _cookie_value(headers.get("cookie"), CSRF_COOKIE)
        header_token = headers.get(CSRF_HEADER)
        if not cookie_token or not header_token:
            return self._forbidden("Missing security token. Reload the page and try again.")
        if not hmac.compare_digest(cookie_token, header_token):
            return self._forbidden("Security token did not match. Reload the page and try again.")
        return None

    @staticmethod
    def _forbidden(detail: str) -> JSONResponse:
        return JSONResponse(
            status_code=403,
            content={"detail": detail, "request_id": current_request_id()},
        )