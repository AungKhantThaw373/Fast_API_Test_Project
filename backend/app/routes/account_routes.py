from datetime import UTC, datetime
from urllib.parse import quote
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_async_session
from app.models.security_models import AuditEvent, AuthSession
from app.schemas.account import (
    AccountDelete,
    AuditEventView,
    AuditListOut,
    MessageOut,
    PasswordChange,
    SessionListOut,
    SessionView,
)
from app.security import AuthContext, get_current_auth, get_password_hash, verify_password
from app.services.account_export import build_account_export
from app.services.audit import record_audit
from app.services.sessions import revoke_all_sessions

router = APIRouter(tags=["account and sessions"])


def _clear_auth_cookies(response: Response) -> None:
    response.delete_cookie(key="token", path="/")
    response.delete_cookie(key="__Host-token", path="/")


@router.get("/sessions", response_model=SessionListOut)
async def list_sessions(
    auth: AuthContext = Depends(get_current_auth),
    session: AsyncSession = Depends(get_async_session),
):
    rows = (await session.scalars(
        select(AuthSession)
        .where(AuthSession.user_id == auth.user.id, AuthSession.revoked_at.is_(None))
        .order_by(AuthSession.last_seen_at.desc())
    )).all()
    return SessionListOut(sessions=[
        SessionView(
            id=row.id,
            user_agent=row.user_agent,
            ip=row.ip,
            created_at=row.created_at,
            last_seen_at=row.last_seen_at,
            current=row.id == auth.session.id,
        )
        for row in rows
    ])


@router.delete("/sessions/{session_id}", response_model=MessageOut)
async def revoke_session(
    session_id: UUID,
    response: Response,
    auth: AuthContext = Depends(get_current_auth),
    session: AsyncSession = Depends(get_async_session),
):
    target = await session.get(AuthSession, session_id)
    if target is None or target.user_id != auth.user.id:
        raise HTTPException(status_code=404, detail="Session not found.")
    if target.revoked_at is None:
        target.revoked_at = datetime.now(UTC)
        await session.commit()
    if target.id == auth.session.id:
        _clear_auth_cookies(response)
    return MessageOut(message="That device has been signed out.")


@router.post("/sessions/revoke-all", response_model=MessageOut)
async def revoke_all(
    response: Response,
    auth: AuthContext = Depends(get_current_auth),
    session: AsyncSession = Depends(get_async_session),
):
    auth.user.token_version += 1
    await revoke_all_sessions(session, auth.user.id)
    await session.commit()
    _clear_auth_cookies(response)
    return MessageOut(message="Signed out everywhere. Sign in again on this device.")


@router.post("/account/password", response_model=MessageOut)
async def change_password(
    payload: PasswordChange,
    response: Response,
    auth: AuthContext = Depends(get_current_auth),
    session: AsyncSession = Depends(get_async_session),
):
    if not verify_password(payload.current_password, auth.user.password):
        raise HTTPException(status_code=400, detail="Current password is incorrect.")
    if payload.current_password == payload.new_password:
        raise HTTPException(status_code=400, detail="Choose a password different from the current one.")
    auth.user.password = get_password_hash(payload.new_password)
    auth.user.token_version += 1
    await revoke_all_sessions(session, auth.user.id)
    record_audit(
        session,
        "password_changed",
        user_id=auth.user.id,
        email=auth.user.email,
        target_type="account",
        target_id=str(auth.user.id),
    )
    await session.commit()
    _clear_auth_cookies(response)
    return MessageOut(message="Password changed. Sign in again with the new password.")


@router.get("/account/audit", response_model=AuditListOut)
async def list_audit_events(
    limit: int = Query(default=50, ge=1, le=200),
    auth: AuthContext = Depends(get_current_auth),
    session: AsyncSession = Depends(get_async_session),
) -> AuditListOut:
    rows = list(await session.scalars(
        select(AuditEvent)
        .where(AuditEvent.user_id == auth.user.id)
        .order_by(AuditEvent.created_at.desc())
        .limit(limit)
    ))
    return AuditListOut(events=[
        AuditEventView(
            id=row.id,
            action=row.action,
            target_type=row.target_type,
            target_id=row.target_id,
            detail=row.detail,
            ip=row.ip,
            created_at=row.created_at,
        )
        for row in rows
    ])


@router.get("/account/export")
async def export_account(
    request: Request,
    auth: AuthContext = Depends(get_current_auth),
    session: AsyncSession = Depends(get_async_session),
) -> Response:
    body, filename = await build_account_export(session, auth.user)
    record_audit(
        session,
        "data_export",
        user_id=auth.user.id,
        email=auth.user.email,
        target_type="account",
        target_id=str(auth.user.id),
        detail={"bytes": len(body), "filename": filename},
        request=request,
    )
    await session.commit()
    return Response(
        content=body,
        media_type="application/zip",
        headers={
            "Content-Disposition": f"attachment; filename=\"{filename}\"; filename*=UTF-8''{quote(filename)}",
            "Cache-Control": "private, no-store",
        },
    )


@router.delete("/account", response_model=MessageOut)
async def delete_account(
    payload: AccountDelete,
    request: Request,
    response: Response,
    auth: AuthContext = Depends(get_current_auth),
    session: AsyncSession = Depends(get_async_session),
) -> MessageOut:
    if payload.confirmation != auth.user.username:
        raise HTTPException(
            status_code=400,
            detail=f"Type your username exactly ({auth.user.username}) to confirm.",
        )
    if not verify_password(payload.password, auth.user.password):
        raise HTTPException(status_code=400, detail="Password is incorrect.")
    # The account is leaving, so its history leaves with it. One anonymised
    # record keeps the deletion auditable without keeping an identifier.
    await session.execute(delete(AuditEvent).where(AuditEvent.user_id == auth.user.id))
    record_audit(
        session,
        "account_deleted",
        user_id=None,
        email="",
        target_type="account",
        target_id="",
        detail={"deleted": True},
        request=request,
    )
    await session.delete(auth.user)
    await session.commit()
    _clear_auth_cookies(response)
    return MessageOut(message="Your account and its data have been deleted.")