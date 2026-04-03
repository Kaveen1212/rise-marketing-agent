"""
app/api/review.py
─────────────────────────────────────────────────────────────────────────────
Human-in-the-Loop review endpoints.
Spec §5.3 — Review Endpoints [reviewer role required]

CRITICAL: Every route here requires reviewer or admin role.
A developer or coordinator JWT must NEVER be able to call these endpoints.
The HITL gate is only as strong as its authentication.

Routes:
  GET  /poster/review/queue              → list all posters awaiting review
  GET  /poster/review/{brief_id}         → load full review interface data
  POST /poster/review/{brief_id}/approve → approve poster for publish
  POST /poster/review/{brief_id}/revise  → request changes from AI
  POST /poster/review/{brief_id}/reject  → hard reject, terminate graph
─────────────────────────────────────────────────────────────────────────────
"""

import structlog
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import UserPayload, get_db, require_reviewer, require_staff
from app.models.brief import PosterBrief, PosterStatus
from app.models.version import PosterVersion
from app.models.review import PosterReview
from app.schemas.review import (
    ApproveRequest,
    ApproveResponse,
    RejectRequest,
    RejectResponse,
    ReviseRequest,
    ReviseResponse,
    ReviewDetailResponse,
    ReviewQueueResponse,
    VersionHistoryItem,
)
from app.services import review_service

log = structlog.get_logger()

router = APIRouter()


def _get_client_ip(request: Request) -> str:
    """
    Extract the real client IP from the request.
    Checks X-Forwarded-For first (set by load balancers) then falls back
    to the direct connection IP.
    """
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        # X-Forwarded-For can be a comma-separated list — first IP is the client
        return forwarded_for.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


# ─────────────────────────────────────────────────────────────────────────────
# GET /poster/review/queue — list all posters awaiting review
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/review/queue", response_model=ReviewQueueResponse)
async def get_review_queue(
    db: AsyncSession = Depends(get_db),
    user: UserPayload = Depends(require_reviewer),
):
    """
    Fetch all posters currently waiting for human review, oldest first.

    Used by the QueueDashboard component to show the marketing head
    how many posters are waiting and how long they have been waiting.
    """
    queue_data = await review_service.get_review_queue(db)
    return ReviewQueueResponse(**queue_data)


# ─────────────────────────────────────────────────────────────────────────────
# GET /poster/review/{brief_id} — load full review interface data
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/review/{brief_id}", response_model=ReviewDetailResponse)
async def get_review_detail(
    brief_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: UserPayload = Depends(require_reviewer),
):
    """
    Load the complete data package for the review interface.

    Returns: brief fields, current poster URLs, QA report,
    and the full version history (every AI attempt with its review outcome).

    The Next.js review page calls this endpoint on load to populate
    the poster preview, QA report panel, brief summary, and version history.
    """
    # Load brief with all versions and reviews eagerly
    result = await db.execute(
        select(PosterBrief)
        .where(PosterBrief.id == brief_id)
        .options(
            selectinload(PosterBrief.versions).selectinload(PosterVersion.reviews),
        )
    )
    brief = result.scalar_one_or_none()

    if brief is None:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Brief not found")

    # Latest version = what the reviewer sees now
    latest = brief.versions[-1] if brief.versions else None

    # Build version history list for the history panel
    history = []
    for v in brief.versions:
        # Find the review decision for this version (if any)
        latest_review = v.reviews[-1] if v.reviews else None
        history.append(
            VersionHistoryItem(
                version_number=v.version_number,
                created_at=v.created_at,
                qa_confidence=float(v.qa_confidence),
                qa_report=v.qa_report,
                poster_urls=v.poster_urls,
                review_decision=latest_review.decision.value if latest_review else None,
                review_feedback=latest_review.feedback if latest_review else None,
            )
        )

    return ReviewDetailResponse(
        brief_id=brief.id,
        topic=brief.topic,
        platforms=brief.platforms,
        languages=brief.languages,
        audience=brief.audience_segment,
        tone=brief.tone,
        key_message=brief.key_message,
        brand_notes=brief.brand_notes,
        revision_count=brief.revision_count,
        poster_urls=latest.poster_urls if latest else {},
        qa_report=latest.qa_report if latest else {},
        qa_confidence=float(latest.qa_confidence) if latest else 0.0,
        version_history=history,
    )


# ─────────────────────────────────────────────────────────────────────────────
# POST /poster/review/{brief_id}/approve
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/review/{brief_id}/approve", response_model=ApproveResponse)
async def approve_poster(
    brief_id: UUID,
    body: ApproveRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: UserPayload = Depends(require_reviewer),
):
    """
    Approve a poster for publication.

    Score validation happens in ApproveRequest (Pydantic):
      - All 4 scores required
      - No score of 1 (critical failure)
      - Average >= REVIEW_APPROVAL_MIN_SCORE (3.5 default)

    After this call:
      - poster_reviews row written (audit log)
      - poster_briefs.status = approved
      - LangGraph graph resumes → publisher_agent schedules posts
      - Posts will go live at Sri Lanka peak hours
    """
    reviewer_id = user.user_id

    result = await review_service.approve_poster(
        db=db,
        brief_id=brief_id,
        reviewer_id=reviewer_id,
        scores=body.scores,
        feedback=body.feedback,
        schedule_override=body.schedule_override,
        ip_address=_get_client_ip(request),
    )

    return ApproveResponse(**result)


# ─────────────────────────────────────────────────────────────────────────────
# POST /poster/review/{brief_id}/revise
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/review/{brief_id}/revise", response_model=ReviseResponse)
async def revise_poster(
    brief_id: UUID,
    body: ReviseRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: UserPayload = Depends(require_reviewer),
):
    """
    Request a revision from the AI designer.

    The feedback string is injected into the designer agent's prompt
    as hard constraints for the next generation cycle.

    Maximum 3 revision cycles per brief (enforced in review_service).
    After 3 failed cycles, the brief status becomes exhausted and must
    be resubmitted as a new campaign.
    """
    reviewer_id = user.user_id

    result = await review_service.revise_poster(
        db=db,
        brief_id=brief_id,
        reviewer_id=reviewer_id,
        scores=body.scores,
        feedback=body.feedback,
        ip_address=_get_client_ip(request),
    )

    return ReviseResponse(**result)


# ─────────────────────────────────────────────────────────────────────────────
# POST /poster/review/{brief_id}/reject
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/review/{brief_id}/reject", response_model=RejectResponse)
async def reject_poster(
    brief_id: UUID,
    body: RejectRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: UserPayload = Depends(require_reviewer),
):
    """
    Hard reject a poster. This terminates the LangGraph graph permanently.

    The brief is returned to the coordinator with the full revision history.
    The reject_reason is stored in the audit log and sent as a notification.

    This action cannot be undone — the brief must be resubmitted as a
    new campaign if the concept is worth pursuing.
    """
    reviewer_id = user.user_id

    result = await review_service.reject_poster(
        db=db,
        brief_id=brief_id,
        reviewer_id=reviewer_id,
        scores=body.scores,
        reject_reason=body.reject_reason,
        ip_address=_get_client_ip(request),
    )

    return RejectResponse(**result)
