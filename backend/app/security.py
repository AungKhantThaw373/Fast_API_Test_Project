from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any
from uuid import UUID, uuid4

import jwt
from fastapi import Cookie, Depends, HTTPException, status
from jwt.exceptions import InvalidTokenError
from pwdlib import PasswordHash
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db import get_async_session
from app.models.app_models import User
from app.models.security_models import AuthSession

password_hash = PasswordHash.recommended()
JWT_REQUIRED_CLAIMS = ["sub", "exp", "iat", "jti", "iss", "aud", "ver"]


def auth_cookie_name() -> str:
    """``__Host-`` requires HTTPS, so local development keeps the short name."""
    return "__Host-token" if settings.APP_ENV == "production" else "token"


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return password_hash.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    return password_hash.hash(password)


def create_access_token(user_id: UUID, token_version: int = 0, jti: UUID | None = None) -> str:
    now = datetime.now(UTC)
    expiry = now + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    return jwt.encode(
        {
            "sub": str(user_id),
            "iat": now,
            "exp": expiry,
            "jti": str(jti or uuid4()),
            "iss": settings.JWT_ISSUER,
            "aud": settings.JWT_AUDIENCE,
            "ver": token_version,
        },
        settings.JWT_SECRET,
        algorithm=settings.ALGORITHM,
    )


def decode_access_token(token: str) -> dict[str, Any]:
    return jwt.decode(
        token,
        settings.JWT_SECRET,
        algorithms=[settings.ALGORITHM],
        audience=settings.JWT_AUDIENCE,
        issuer=settings.JWT_ISSUER,
        options={"require": JWT_REQUIRED_CLAIMS},
    )


@dataclass
class AuthContext:
    user: User
    session: AuthSession


async def get_current_auth(
    token: Annotated[str | None, Cookie()] = None,
    host_token: Annotated[str | None, Cookie(alias="__Host-token")] = None,
    session: AsyncSession = Depends(get_async_session),
) -> AuthContext:
    token = host_token or token
    unauthenticated = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Please sign in to continue.",
    )
    if not token:
        raise unauthenticated
    try:
        payload = decode_access_token(token)
        subject = str(payload["sub"])
        jti = UUID(str(payload["jti"]))
        token_version = int(payload["ver"])
    except (InvalidTokenError, KeyError, TypeError, ValueError):
        raise unauthenticated from None

    try:
        user = await session.scalar(select(User).where(User.id == UUID(subject)))
    except ValueError:
        user = None
    if user is None or user.token_version != token_version:
        raise unauthenticated

    auth_session = await session.get(AuthSession, jti)
    if (
        auth_session is None
        or auth_session.user_id != user.id
        or auth_session.revoked_at is not None
    ):
        raise unauthenticated

    now = datetime.now(UTC)
    if auth_session.last_seen_at < now - timedelta(minutes=1):
        auth_session.last_seen_at = now
        await session.commit()
    return AuthContext(user=user, session=auth_session)


async def get_current_user(auth: AuthContext = Depends(get_current_auth)) -> User:
    return auth.user