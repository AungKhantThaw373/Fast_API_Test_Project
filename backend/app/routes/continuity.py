"""Continuity endpoints: latest scan, run a check, and review findings."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_async_session
from app.models.app_models import User
from app.schemas.continuity import (
    FindingOut,
    FindingReviewOut,
    FindingReviewUpdate,
    IntentionalOut,
    IntentionalUpdate,
    LatestScanOut,
    ScanCheckOut,
    ScanJobOut,
    ScanSummaryOut,
)
from app.security import get_current_user
from app.services import chapters as chapters_service
from app.services import continuity as continuity_service
from app.services import jobs as jobs_service
from app.services import stories as stories_service

router = APIRouter(prefix="/stories", tags=["continuity"])


@router.get("/chapters/{chapter_id}/scan", response_model=LatestScanOut)
async def get_latest_scan(
    chapter_id: UUID,
    limit: int | None = Query(default=None, ge=1, le=1000),
    cursor: str | None = Query(default=None),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
) -> LatestScanOut:
    chapter = await chapters_service.owned_chapter(session, chapter_id, user.id)
    scan, findings, next_cursor = await continuity_service.latest_scan(
        session, chapter.id, limit=limit, cursor=cursor
    )
    return LatestScanOut(
        scan=ScanSummaryOut.model_validate(scan) if scan else None,
        findings=[
            FindingOut(
                id=item.id,
                draft_quote=item.draft_quote,
                draft_line=item.draft_line,
                earlier_quote=item.earlier_quote,
                earlier_chapter_id=item.earlier_chapter_id,
                earlier_chapter_number=item.earlier_chapter_number,
                earlier_chapter_title=title if item.source == "llm" else "",
                explanation=item.explanation,
                confidence=item.confidence,
                intentional=item.intentional,
                review_status=item.review_status,
                source=item.source,
                rule_id=item.rule_id,
                scene_index=item.scene_index,
                evidence_kind=item.evidence_kind,
                evidence_id=item.evidence_id,
            )
            for item, title in findings
        ],
        next_cursor=next_cursor,
    )


@router.post("/chapters/{chapter_id}/scan-job", response_model=ScanJobOut)
async def queue_chapter_scan(
    chapter_id: UUID,
    force: bool = False,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
) -> ScanJobOut:
    chapter = await chapters_service.owned_chapter(session, chapter_id, user.id)
    story = await stories_service.owned_story(session, chapter.story_id, user.id)
    await continuity_service.assert_ready_for_scan(session, story, chapter, user.id)
    job_id = await jobs_service.enqueue(
        session,
        "continuity_scan",
        {"chapter_id": str(chapter.id), "owner_id": str(user.id), "force": force},
        owner_id=user.id,
        dedupe_key=f"continuity:{chapter.id}:{int(force)}",
        max_attempts=2,
    )
    if job_id is None:
        raise HTTPException(
            status_code=409,
            detail="A continuity check is already running for this chapter.",
        )
    return ScanJobOut(job_id=job_id)


@router.post("/chapters/{chapter_id}/scan", response_model=ScanCheckOut)
async def check_chapter_continuity(
    chapter_id: UUID,
    force: bool = False,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
) -> ScanCheckOut:
    chapter = await chapters_service.owned_chapter(session, chapter_id, user.id)
    story = await stories_service.owned_story(session, chapter.story_id, user.id)
    await continuity_service.assert_ready_for_scan(session, story, chapter, user.id)
    scan, finding_count, reused = await continuity_service.check_chapter(
        session, story, chapter, user.id, force=force
    )
    return ScanCheckOut(
        scan_id=scan.id,
        finding_count=finding_count,
        chapter_revision=scan.chapter_revision,
        reused=reused,
    )


@router.patch("/findings/{finding_id}/intentional", response_model=IntentionalOut)
async def mark_finding_intentional(
    finding_id: UUID,
    payload: IntentionalUpdate,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
) -> IntentionalOut:
    finding = await continuity_service.owned_finding(session, finding_id, user.id)
    finding.intentional = payload.intentional
    if payload.intentional:
        finding.review_status = "dismissed"
    elif finding.review_status == "dismissed":
        finding.review_status = "open"
    await session.commit()
    return IntentionalOut(id=finding.id, intentional=finding.intentional)


@router.patch("/findings/{finding_id}/review", response_model=FindingReviewOut)
async def review_finding(
    finding_id: UUID,
    payload: FindingReviewUpdate,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
) -> FindingReviewOut:
    finding = await continuity_service.owned_finding(session, finding_id, user.id)
    finding.review_status = payload.review_status
    if payload.review_status == "dismissed":
        finding.intentional = True
    elif payload.review_status == "open":
        finding.intentional = False
    await session.commit()
    return FindingReviewOut(
        id=finding.id,
        review_status=finding.review_status,
        intentional=finding.intentional,
    )
