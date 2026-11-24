"""Job status for polling clients."""

from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_async_session
from app.models.app_models import User
from app.models.job_models import Job
from app.schemas.jobs import JobOut
from app.security import get_current_user
from app.services import jobs as jobs_service

router = APIRouter(tags=["jobs"])


@router.get("/jobs/{job_id}", response_model=JobOut)
async def get_job(
    job_id: UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
) -> Job:
    return await jobs_service.owned_job(session, job_id, user.id)
