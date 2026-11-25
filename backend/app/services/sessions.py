"""Auth session helpers shared by login, logout, and account routes."""

from datetime import UTC, datetime

from fastapi import Request
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.app_models import User
from app.models.security_models import AuthSession


def request_ip(request: Request) -> str:
    return request.client.host if request.client and request.client.host else "unknown"


async def create_auth_session(session: AsyncSession, user: User, request: Request) -> AuthSession:
    auth_session = AuthSession(
        user_id=user.id,
        user_agent=(request.headers.get("user-agent") or "")[:400],
        ip=request_ip(request),
    )
    session.add(auth_session)
    await session.flush()
    return auth_session


async def revoke_all_sessions(session: AsyncSession, user_id) -> None:
    await session.execute(
        update(AuthSession)
        .where(AuthSession.user_id == user_id, AuthSession.revoked_at.is_(None))
        .values(revoked_at=datetime.now(UTC))
    )