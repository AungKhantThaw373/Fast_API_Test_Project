import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db import get_async_session
from app.models.app_models import User
from app.models.security_models import AuthSession, LoginAttempt, PasswordResetToken
from app.rate_limits import (
    LOGIN_LIMIT,
    LOGIN_WINDOW_SECONDS,
    client_ip,
    limiter,
    password_reset_rate_limit,
    register_rate_limit,
)
from app.schemas.account import MessageOut, PasswordResetConfirm, PasswordResetRequest
from app.schemas.auth import UserCreate, normalize_email
from app.security import (
    AuthContext,
    auth_cookie_name,
    create_access_token,
    get_current_auth,
    get_password_hash,
    verify_password,
)
from app.services.audit import record_audit
from app.services.email import send_password_reset
from app.services.sessions import revoke_all_sessions

router = APIRouter(tags=["authentication"])
RESET_TOKEN_MINUTES = 30
SECURITY_RETENTION_DAYS = 30


async def _record_attempt(session: AsyncSession, ip: str, email: str, success: bool) -> None:
    session.add(LoginAttempt(ip=ip, email=email, success=success))
    await session.commit()


async def _recent_failures(session: AsyncSession, email: str) -> int:
    cutoff = datetime.now(UTC) - timedelta(seconds=LOGIN_WINDOW_SECONDS)
    return int(await session.scalar(
        select(func.count(LoginAttempt.id)).where(
            LoginAttempt.email == email,
            LoginAttempt.success.is_(False),
            LoginAttempt.created_at >= cutoff,
        )
    ) or 0)


def _set_auth_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=auth_cookie_name(),
        value=token,
        httponly=True,
        secure=settings.COOKIE_SECURE,
        samesite="lax",
        max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        path="/",
    )


def _clear_auth_cookies(response: Response) -> None:
    response.delete_cookie(key="token", path="/")
    response.delete_cookie(key="__Host-token", path="/")


@router.post("/register", status_code=status.HTTP_201_CREATED, dependencies=[Depends(register_rate_limit)])
async def register(
    user_in: UserCreate,
    session: AsyncSession = Depends(get_async_session),
):
    exists = await session.scalar(
        select(User.id).where(
            (func.lower(User.email) == user_in.email.strip().lower())
            | (User.username == user_in.username)
        )
    )
    if exists:
        raise HTTPException(status_code=409, detail="That email or username is already in use.")

    user = User(
        username=user_in.username,
        email=user_in.email,
        password=get_password_hash(user_in.password),
    )
    session.add(user)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise HTTPException(status_code=409, detail="That email or username is already in use.") from None
    await session.refresh(user)
    return {"id": str(user.id), "username": user.username, "email": user.email}


@router.post("/token")
async def login(
    request: Request,
    response: Response,
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    session: AsyncSession = Depends(get_async_session),
):
    email = normalize_email(form_data.username)
    ip = client_ip(request)
    now = datetime.now(UTC)
    lockout = ("Too many failed sign-in attempts. Try again in 15 minutes.", LOGIN_WINDOW_SECONDS)

    # Five failures lock the account even when the attacker changes IP. The
    # last success deletes the failures, so a normal sign-in clears the count.
    if await _recent_failures(session, email) >= LOGIN_LIMIT:
        await _record_attempt(session, ip, email, False)
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=lockout[0],
            headers={"Retry-After": str(lockout[1])},
        )
    ip_retry = limiter.peek(f"login-ip:{ip}", LOGIN_LIMIT, LOGIN_WINDOW_SECONDS)
    if ip_retry is not None:
        await _record_attempt(session, ip, email, False)
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many failed sign-in attempts from this address. Try again later.",
            headers={"Retry-After": str(ip_retry)},
        )

    user = await session.scalar(select(User).where(func.lower(User.email) == email))
    if user is None or not verify_password(form_data.password, user.password):
        limiter.consume(f"login-ip:{ip}", LOGIN_LIMIT, LOGIN_WINDOW_SECONDS)
        await _record_attempt(session, ip, email, False)
        raise HTTPException(status_code=401, detail="Email or password is incorrect.")

    # Clear accumulated failures for this account and address after a real
    # sign-in. The successful row remains in the audit trail.
    await session.execute(delete(LoginAttempt).where(
        LoginAttempt.email == email, LoginAttempt.success.is_(False)
    ))
    await session.execute(delete(LoginAttempt).where(
        LoginAttempt.ip == ip, LoginAttempt.success.is_(False)
    ))
    # Keep the security trail useful without letting it grow forever.
    cutoff = now - timedelta(days=SECURITY_RETENTION_DAYS)
    await session.execute(delete(LoginAttempt).where(LoginAttempt.created_at < cutoff))
    await session.execute(delete(AuthSession).where(
        AuthSession.revoked_at.is_not(None), AuthSession.revoked_at < cutoff
    ))
    await session.execute(delete(PasswordResetToken).where(
        PasswordResetToken.expires_at < cutoff
    ))
    await session.commit()
    limiter.reset(f"login-ip:{ip}")
    await _record_attempt(session, ip, email, True)

    auth_session = AuthSession(
        user_id=user.id,
        user_agent=(request.headers.get("user-agent") or "")[:400],
        ip=ip,
    )
    session.add(auth_session)
    await session.flush()
    access_token = create_access_token(user.id, user.token_version, auth_session.id)
    await session.commit()

    _set_auth_cookie(response, access_token)
    return {"message": "Signed in."}


@router.post("/logout", response_model=MessageOut)
async def logout(
    auth: AuthContext = Depends(get_current_auth),
    session: AsyncSession = Depends(get_async_session),
):
    response = Response()
    auth.session.revoked_at = datetime.now(UTC)
    await session.commit()
    _clear_auth_cookies(response)
    return MessageOut(message="Signed out.")


@router.post("/forgot-password", status_code=status.HTTP_202_ACCEPTED, response_model=MessageOut)
async def forgot_password(
    payload: PasswordResetRequest,
    request: Request,
    _limit: None = Depends(password_reset_rate_limit),
    session: AsyncSession = Depends(get_async_session),
):
    email = normalize_email(payload.email)
    user = await session.scalar(select(User).where(func.lower(User.email) == email))
    if user is not None:
        now = datetime.now(UTC)
        await session.execute(
            update(PasswordResetToken)
            .where(PasswordResetToken.user_id == user.id, PasswordResetToken.used_at.is_(None))
            .values(used_at=now)
        )
        raw_token = secrets.token_urlsafe(32)
        session.add(PasswordResetToken(
            user_id=user.id,
            token_hash=hashlib.sha256(raw_token.encode()).hexdigest(),
            expires_at=now + timedelta(minutes=RESET_TOKEN_MINUTES),
        ))
        record_audit(
            session,
            "password_reset_requested",
            user_id=user.id,
            email=user.email,
            target_type="account",
            target_id=str(user.id),
            request=request,
        )
        await session.commit()
        link = f"{settings.FRONTEND_URL.rstrip('/')}/reset?token={quote(raw_token)}"
        await send_password_reset(user.email, link)
    # The same answer for unknown addresses avoids an account-enumeration oracle.
    return MessageOut(message="If that email is registered, a reset link has been sent.")


@router.post("/reset-password", response_model=MessageOut)
async def reset_password(
    payload: PasswordResetConfirm,
    request: Request,
    session: AsyncSession = Depends(get_async_session),
):
    digest = hashlib.sha256(payload.token.encode()).hexdigest()
    now = datetime.now(UTC)
    user_id = await session.scalar(
        update(PasswordResetToken)
        .where(
            PasswordResetToken.token_hash == digest,
            PasswordResetToken.used_at.is_(None),
            PasswordResetToken.expires_at > now,
        )
        .values(used_at=now)
        .returning(PasswordResetToken.user_id)
    )
    if user_id is None:
        await session.rollback()
        raise HTTPException(status_code=400, detail="That reset link is invalid or has expired.")
    user = await session.get(User, user_id)
    if user is None:
        await session.rollback()
        raise HTTPException(status_code=400, detail="That reset link is invalid or has expired.")
    user.password = get_password_hash(payload.new_password)
    user.token_version += 1
    await revoke_all_sessions(session, user.id)
    await session.execute(delete(LoginAttempt).where(LoginAttempt.email == user.email))
    record_audit(
        session,
        "password_reset",
        user_id=user.id,
        email=user.email,
        target_type="account",
        target_id=str(user.id),
        request=request,
    )
    await session.commit()
    return MessageOut(message="Password changed. Sign in with the new password.")