"""
app/api/briefs.py
─────────────────────────────────────────────────────────────────────────────
Brief submission and pipeline status endpoints.
Spec §5.2 — Brief & Generation Endpoints

Routes:
  POST   /poster/briefs           → submit brief, start pipeline
  GET    /poster/briefs           → list all briefs with filters
  GET    /poster/briefs/{id}      → get one brief + pipeline status
  DELETE /poster/briefs/{id}      → cancel brief (only if still generating)
─────────────────────────────────────────────────────────────────────────────
"""

import structlog
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import UserPayload, get_db, require_staff
from app.models.brief import PosterBrief, PosterStatus
from app.schemas.brief import (
    BriefCancelResponse,
    BriefCreate,
    BriefDetail,
    BriefListItem,
    BriefListResponse,
    BriefSubmitResponse,
)
from app.services import pipeline_service

log = structlog.get_logger()

router = APIRouter()

# Statuses that mean the pipeline is still running — can be cancelled
CANCELLABLE_STATUSES = {PosterStatus.GENERATING, PosterStatus.QA_CHECK}


# ─────────────────────────────────────────────────────────────────────────────
# POST /poster/briefs — submit a new brief and start the pipeline
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/briefs", response_model=BriefSubmitResponse, status_code=201)
async def submit_brief(
    body: BriefCreate,
    db: AsyncSession = Depends(get_db),
    user: UserPayload = Depends(require_staff),
):
    """
    Submit a new campaign brief.

    Creates a poster_briefs row and starts the LangGraph pipeline.
    The pipeline runs asynchronously — this endpoint returns immediately
    with the brief_id. Poll GET /briefs/{id} to track progress.

    The pipeline will pause at the HITL gate (pending_review status)
    and wait for a human reviewer to act via the /review endpoints.
    """
    # Create the DB row first so we have a UUID to use as the thread_id
    brief = PosterBrief(
        # thread_id = brief.id — same UUID used for both DB and LangGraph
        # Set after flush() gives us the UUID
        thread_id="placeholder",
        submitted_by=user.user_id,
        topic=body.topic,
        platforms=body.platforms,
        languages=body.languages,
        audience_segment=body.audience,
        tone=body.tone,
        key_message=body.key_message,
        brand_notes=body.brand_notes,
        status=PosterStatus.GENERATING,
    )
    db.add(brief)
    await db.flush()  # generates brief.id

    # Now set thread_id = the generated UUID (they must be the same)
    brief.thread_id = str(brief.id)
    await db.flush()

    log.info("brief_submitted", brief_id=str(brief.id), topic=body.topic)

    # Build the initial LangGraph state from the brief data
    from app.graph.state import PosterState
    initial_state: PosterState = {
        "brief_id":        str(brief.id),
        "campaign_topic":  brief.topic,
        "platforms":       brief.platforms,
        "languages":       brief.languages,
        "tone":            brief.tone,
        "audience_segment": brief.audience_segment,
        # Agent outputs — empty until each agent runs
        "headline":        {},
        "body_copy":       {},
        "cta":             {},
        "hashtags":        {},
        "image_prompt":    "",
        "image_url":       "",
        "design_manifest": {},
        "poster_urls":     {},
        "qa_report":       {},
        "qa_confidence":   0.0,
        "revision_count":  0,
        # HITL fields — empty until human reviews
        "review_status":   "pending",
        "review_scores":   None,
        "review_feedback": None,
        "reviewer_id":     None,
        "reviewed_at":     None,
        # Publisher fields — empty until approved
        "scheduled_at":    None,
        "published_post_ids": None,
        "analytics_24h":   None,
    }

    # Start the pipeline in the background
    # It runs until interrupt_before=["human_review"] fires and pauses
    await pipeline_service.start_pipeline(str(brief.id), initial_state)

    # Pipeline has paused at HITL gate — update status to pending_review
    brief.status = PosterStatus.PENDING_REVIEW
    await db.flush()

    # Notify reviewers that a poster is ready — non-fatal if it fails
    try:
        from app.services.notification_service import notify_pending_review
        await notify_pending_review(brief)
    except Exception as exc:
        log.warning("pending_review_notification_failed", error=str(exc))

    return BriefSubmitResponse(
        brief_id=brief.id,
        thread_id=brief.thread_id,
        status=brief.status.value,
        eta_seconds=90,
    )


# ─────────────────────────────────────────────────────────────────────────────
# GET /poster/briefs — list all briefs with optional filters
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/briefs", response_model=BriefListResponse)
async def list_briefs(
    status: str | None = Query(default=None, description="Filter by pipeline status"),
    platform: str | None = Query(default=None, description="Filter by target platform"),
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    user: UserPayload = Depends(require_staff),
):
    """
    List all briefs with optional status and platform filters.
    Results are paginated — use ?page= and ?limit= to navigate.
    """
    query = select(PosterBrief).order_by(PosterBrief.created_at.desc())

    if status:
        try:
            status_enum = PosterStatus(status)
            query = query.where(PosterBrief.status == status_enum)
        except ValueError:
            raise HTTPException(
                status_code=422,
                detail=f"Invalid status '{status}'. Valid values: {[s.value for s in PosterStatus]}",
            )

    if platform:
        # ARRAY contains check — brief.platforms is a TEXT[] column
        query = query.where(PosterBrief.platforms.contains([platform]))

    # Count total before pagination
    count_result = await db.execute(
        select(func.count()).select_from(query.subquery())
    )
    total = count_result.scalar_one()

    # Apply pagination
    offset = (page - 1) * limit
    query = query.offset(offset).limit(limit)

    result = await db.execute(query)
    briefs = result.scalars().all()

    items = [
        BriefListItem(
            brief_id=b.id,
            topic=b.topic,
            platforms=b.platforms,
            languages=b.languages,
            status=b.status.value,
            revision_count=b.revision_count,
            created_at=b.created_at,
        )
        for b in briefs
    ]

    return BriefListResponse(briefs=items, total=total, page=page)


# ─────────────────────────────────────────────────────────────────────────────
# GET /poster/briefs/{brief_id} — get one brief + live pipeline status
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/briefs/{brief_id}", response_model=BriefDetail)
async def get_brief(
    brief_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: UserPayload = Depends(require_staff),
):
    """
    Get full detail for one brief plus its current pipeline position.

    current_node comes from the LangGraph checkpointer — it shows which
    agent is running or which node the graph is waiting at.
    """
    brief = await db.get(PosterBrief, brief_id)
    if brief is None:
        raise HTTPException(status_code=404, detail="Brief not found")

    # Read live position from LangGraph checkpointer
    pipeline_info = await pipeline_service.get_pipeline_status(brief.thread_id)

    return BriefDetail(
        brief_id=brief.id,
        thread_id=brief.thread_id,
        topic=brief.topic,
        platforms=brief.platforms,
        languages=brief.languages,
        audience=brief.audience_segment,
        tone=brief.tone,
        key_message=brief.key_message,
        brand_notes=brief.brand_notes,
        status=brief.status.value,
        revision_count=brief.revision_count,
        created_at=brief.created_at,
        current_node=pipeline_info.get("current_node"),
        qa_confidence=pipeline_info.get("qa_confidence"),
    )


# ─────────────────────────────────────────────────────────────────────────────
# DELETE /poster/briefs/{brief_id} — cancel a brief in generation
# ─────────────────────────────────────────────────────────────────────────────

@router.delete("/briefs/{brief_id}", response_model=BriefCancelResponse)
async def cancel_brief(
    brief_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: UserPayload = Depends(require_staff),
):
    """
    Cancel a brief that is still being generated.

    Cannot cancel briefs that are pending_review, approved, or published —
    those have already passed the HITL gate or are live.
    """
    brief = await db.get(PosterBrief, brief_id)
    if brief is None:
        raise HTTPException(status_code=404, detail="Brief not found")

    if brief.status not in CANCELLABLE_STATUSES:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Cannot cancel brief with status '{brief.status.value}'. "
                f"Only {[s.value for s in CANCELLABLE_STATUSES]} briefs can be cancelled."
            ),
        )

    brief.status = PosterStatus.REJECTED
    brief.completed_at = datetime.now(timezone.utc)

    log.info("brief_cancelled", brief_id=str(brief_id))

    return BriefCancelResponse(cancelled=True)
