from datetime import datetime, timedelta, timezone
from typing import Annotated
from uuid import UUID

import jwt
from fastapi import Cookie, Depends, HTTPException, status
from jwt.exceptions import InvalidTokenError
from pwdlib import PasswordHash
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db import get_async_session
from app.models.app_models import User


password_hash = PasswordHash.recommended()


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return password_hash.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    return password_hash.hash(password)


def create_access_token(user_id: UUID) -> str:
    expiry = datetime.now(timezone.utc) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    return jwt.encode(
        {"sub": str(user_id), "exp": expiry},
        settings.JWT_SECRET,
        algorithm=settings.ALGORITHM,
    )


async def get_current_user(
    token: Annotated[str | None, Cookie()] = None,
    session: AsyncSession = Depends(get_async_session),
) -> User:
    unauthenticated = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Please sign in to continue.",
    )
    if not token:
        raise unauthenticated
    try:
        subject = jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.ALGORITHM]).get("sub")
        if not subject:
            raise unauthenticated
    except (InvalidTokenError, TypeError):
        raise unauthenticated from None

    try:
        user = await session.scalar(select(User).where(User.id == UUID(subject)))
    except ValueError:
        # Accept unexpired sessions issued by the previous username-subject login.
        user = await session.scalar(select(User).where(User.username == subject))
    if user is None:
        raise unauthenticated
    return user
