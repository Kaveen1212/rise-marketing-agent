"""
app/services/review_service.py
─────────────────────────────────────────────────────────────────────────────
Business logic for the three human review decisions.

The API route (review.py) validates the request and calls one of these
functions. This layer owns:
  - Loading and verifying brief state before acting
  - Writing the audit record to poster_reviews
  - Updating poster_briefs.status
  - Resuming the LangGraph graph via pipeline_service
  - Sending notifications
─────────────────────────────────────────────────────────────────────────────
"""

import structlog
from datetime import datetime, timezone, timedelta
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import settings
from app.models.brief import PosterBrief, PosterStatus
from app.models.review import PosterReview, ReviewDecision
from app.models.version import PosterVersion
from app.schemas.review import ReviewScores
from app.services import pipeline_service

log = structlog.get_logger()


# ─────────────────────────────────────────────────────────────────────────────
# Shared helper — load brief and verify it is in a reviewable state
# ─────────────────────────────────────────────────────────────────────────────

async def _load_reviewable_brief(db: AsyncSession, brief_id: UUID) -> PosterBrief:
    """
    Load the brief and verify it is currently pending_review.
    Raises 404 if not found, 409 if not in a reviewable state.
    """
    brief = await db.get(PosterBrief, brief_id)

    if brief is None:
        raise HTTPException(status_code=404, detail="Brief not found")

    if brief.status != PosterStatus.PENDING_REVIEW:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Brief is not awaiting review. "
                f"Current status: {brief.status.value}"
            ),
        )
    return brief


async def _get_latest_version(db: AsyncSession, brief_id: UUID) -> PosterVersion | None:
    """Return the latest poster_versions row for a brief."""
    result = await db.execute(
        select(PosterVersion)
        .where(PosterVersion.brief_id == brief_id)
        .order_by(PosterVersion.version_number.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


def _write_review_record(
    db: AsyncSession,
    brief: PosterBrief,
    version: PosterVersion | None,
    reviewer_id: UUID,
    decision: ReviewDecision,
    scores: ReviewScores,
    feedback: str | None,
    ip_address: str,
) -> PosterReview:
    """Create and stage (but not commit) a poster_reviews row."""
    review = PosterReview(
        brief_id=brief.id,
        version_id=version.id if version else None,
        reviewer_id=reviewer_id,
        decision=decision,
        score_brand=scores.brand,
        score_clarity=scores.clarity,
        score_visual=scores.visual,
        score_cultural=scores.cultural,
        feedback=feedback,
        ip_address=ip_address,
    )
    db.add(review)
    return review


# ─────────────────────────────────────────────────────────────────────────────
# approve_poster
# ─────────────────────────────────────────────────────────────────────────────

async def approve_poster(
    db: AsyncSession,
    brief_id: UUID,
    reviewer_id: UUID,
    scores: ReviewScores,
    feedback: str | None,
    schedule_override: datetime | None,
    ip_address: str,
) -> dict:
    """
    Approve a poster for publication.

    1. Load brief — verify status == pending_review
    2. Write audit record to poster_reviews
    3. Update poster_briefs.status = approved
    4. Resume the LangGraph graph → routes to publisher_agent
    5. Return the scheduled publish times

    Returns:
        { "approved": True, "scheduled_at": { "instagram": "...", ... } }
    """
    brief = await _load_reviewable_brief(db, brief_id)
    version = await _get_latest_version(db, brief_id)

    # Write the audit record
    _write_review_record(
        db=db,
        brief=brief,
        version=version,
        reviewer_id=reviewer_id,
        decision=ReviewDecision.APPROVED,
        scores=scores,
        feedback=feedback,
        ip_address=ip_address,
    )

    # Update brief status
    brief.status = PosterStatus.APPROVED
    await db.flush()

    log.info(
        "poster_approved",
        brief_id=str(brief_id),
        reviewer_id=str(reviewer_id),
        avg_score=scores.average,
    )

    # Resume the graph — publisher_agent will call schedule_post() for each platform
    state_update = {
        "review_status":   "approved",
        "reviewer_id":     str(reviewer_id),
        "review_scores":   scores.model_dump(),
        "review_feedback": feedback,
        "reviewed_at":     datetime.now(timezone.utc).isoformat(),
    }
    if schedule_override:
        state_update["schedule_override"] = schedule_override.isoformat()

    await pipeline_service.resume_pipeline(brief.thread_id, state_update)

    # Build scheduled_at preview from config defaults for the response
    from app.services.publish_service import calculate_publish_time
    scheduled_at = {
        platform: calculate_publish_time(platform, schedule_override).isoformat()
        for platform in brief.platforms
    }

    return {"approved": True, "scheduled_at": scheduled_at}


# ─────────────────────────────────────────────────────────────────────────────
# revise_poster
# ─────────────────────────────────────────────────────────────────────────────

async def revise_poster(
    db: AsyncSession,
    brief_id: UUID,
    reviewer_id: UUID,
    scores: ReviewScores,
    feedback: str,
    ip_address: str,
) -> dict:
    """
    Request a revision — send the poster back to the designer agent.

    1. Load brief — verify status == pending_review AND revision_count < 3
    2. Write audit record
    3. Increment revision_count
    4. Update status = in_revision
    5. Resume graph → designer_agent receives feedback as hard constraints

    Returns:
        { "revision_number": 1, "regenerating": True, "eta_seconds": 90 }
    """
    brief = await _load_reviewable_brief(db, brief_id)

    # Hard limit: 3 revision cycles maximum (spec §4.3 + DB CHECK constraint)
    if brief.revision_count >= settings.REVIEW_MAX_REVISIONS:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Maximum revision cycles ({settings.REVIEW_MAX_REVISIONS}) reached. "
                "Brief must be resubmitted as a new campaign."
            ),
        )

    version = await _get_latest_version(db, brief_id)

    _write_review_record(
        db=db,
        brief=brief,
        version=version,
        reviewer_id=reviewer_id,
        decision=ReviewDecision.REVISION,
        scores=scores,
        feedback=feedback,
        ip_address=ip_address,
    )

    brief.revision_count += 1
    brief.status = PosterStatus.IN_REVISION
    await db.flush()

    log.info(
        "poster_revision_requested",
        brief_id=str(brief_id),
        reviewer_id=str(reviewer_id),
        revision_number=brief.revision_count,
    )

    # Resume graph — designer_agent will receive feedback as constraints
    state_update = {
        "review_status":   "revision",
        "reviewer_id":     str(reviewer_id),
        "review_scores":   scores.model_dump(),
        "review_feedback": feedback,
        "revision_count":  brief.revision_count,
        "reviewed_at":     datetime.now(timezone.utc).isoformat(),
    }

    await pipeline_service.resume_pipeline(brief.thread_id, state_update)

    return {
        "revision_number": brief.revision_count,
        "regenerating":    True,
        "eta_seconds":     90,
    }


# ─────────────────────────────────────────────────────────────────────────────
# reject_poster
# ─────────────────────────────────────────────────────────────────────────────

async def reject_poster(
    db: AsyncSession,
    brief_id: UUID,
    reviewer_id: UUID,
    scores: ReviewScores,
    reject_reason: str,
    ip_address: str,
) -> dict:
    """
    Hard reject — terminates the graph. Brief is returned to the coordinator.

    1. Load brief
    2. Write audit record
    3. Update status = rejected
    4. Resume graph → routes to END (no publish ever)
    5. Send notification to coordinator

    Returns:
        { "rejected": True, "brief_returned": True }
    """
    brief = await _load_reviewable_brief(db, brief_id)
    version = await _get_latest_version(db, brief_id)

    _write_review_record(
        db=db,
        brief=brief,
        version=version,
        reviewer_id=reviewer_id,
        decision=ReviewDecision.REJECTED,
        scores=scores,
        feedback=reject_reason,
        ip_address=ip_address,
    )

    brief.status = PosterStatus.REJECTED
    brief.completed_at = datetime.now(timezone.utc)
    await db.flush()

    log.info(
        "poster_rejected",
        brief_id=str(brief_id),
        reviewer_id=str(reviewer_id),
        reason=reject_reason,
    )

    # Resume graph with rejected status → route_after_review returns "rejected" → END
    state_update = {
        "review_status":   "rejected",
        "reviewer_id":     str(reviewer_id),
        "review_scores":   scores.model_dump(),
        "review_feedback": reject_reason,
        "reviewed_at":     datetime.now(timezone.utc).isoformat(),
    }

    await pipeline_service.resume_pipeline(brief.thread_id, state_update)

    # Notify the coordinator — non-fatal if it fails
    try:
        from app.services.notification_service import notify_rejected
        await notify_rejected(brief, reject_reason)
    except Exception as exc:
        log.warning("rejection_notification_failed", error=str(exc))

    return {"rejected": True, "brief_returned": True}


# ─────────────────────────────────────────────────────────────────────────────
# get_review_queue
# ─────────────────────────────────────────────────────────────────────────────

async def get_review_queue(db: AsyncSession) -> dict:
    """
    Return all briefs currently waiting for human review, oldest first.

    Used by GET /poster/review/queue and the QueueDashboard frontend component.

    Returns:
        {
          "posters": [...],
          "count": int,
          "oldest_pending_age_hours": float | None
        }
    """
    result = await db.execute(
        select(PosterBrief)
        .where(PosterBrief.status == PosterStatus.PENDING_REVIEW)
        .order_by(PosterBrief.created_at.asc())
        .options(selectinload(PosterBrief.versions))
    )
    briefs = result.scalars().all()

    now = datetime.now(timezone.utc)
    items = []
    oldest_age_hours = None

    for brief in briefs:
        latest_version = brief.versions[-1] if brief.versions else None
        age_hours = (now - brief.created_at).total_seconds() / 3600

        if oldest_age_hours is None or age_hours > oldest_age_hours:
            oldest_age_hours = age_hours

        items.append({
            "brief_id":       brief.id,
            "topic":          brief.topic,
            "platforms":      brief.platforms,
            "languages":      brief.languages,
            "created_at":     brief.created_at,
            "revision_count": brief.revision_count,
            "qa_confidence":  float(latest_version.qa_confidence) if latest_version else None,
            "poster_url":     None,   # S3 presigned URL — added by storage_service
        })

    return {
        "posters":                items,
        "count":                  len(items),
        "oldest_pending_age_hours": round(oldest_age_hours, 1) if oldest_age_hours else None,
    }
