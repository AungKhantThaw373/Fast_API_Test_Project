"""Owner-readable audit trail for sensitive actions."""

from typing import Any

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.security_models import AuditEvent
from app.services.sessions import request_ip


def record_audit(
    session: AsyncSession,
    action: str,
    *,
    user_id: Any = None,
    email: str = "",
    target_type: str = "",
    target_id: str = "",
    detail: dict[str, Any] | None = None,
    request: Request | None = None,
) -> AuditEvent:
    event = AuditEvent(
        user_id=user_id,
        email=email,
        action=action,
        target_type=target_type,
        target_id=target_id,
        detail=detail or {},
        ip=request_ip(request) if request is not None else "",
    )
    session.add(event)
    return event