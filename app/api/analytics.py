"""
app/api/analytics.py
─────────────────────────────────────────────────────────────────────────────
Analytics and monitoring endpoints.
Spec §5.4 — Analytics & Monitoring Endpoints

Routes:
  GET /poster/analytics/published   → engagement metrics for all published posts
  GET /poster/analytics/quality     → review scores and approval rate trends
  GET /poster/analytics/agent-costs → LangSmith cost data
  GET /poster/queue/status          → live count per pipeline stage
─────────────────────────────────────────────────────────────────────────────
"""

from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import cast, Float, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import UserPayload, get_db, require_staff
from app.models.brief import PosterBrief, PosterStatus
from app.models.publication import PosterPublication, PublicationStatus
from app.models.review import PosterReview, ReviewDecision
from app.schemas.analytics import (
    AgentCostResponse,
    PublishedAnalyticsResponse,
    PublishedPostSummary,
    QualityAnalyticsResponse,
    QueueStatusResponse,
)

router = APIRouter()


# ─────────────────────────────────────────────────────────────────────────────
# GET /poster/analytics/published
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/analytics/published", response_model=PublishedAnalyticsResponse)
async def get_published_analytics(
    db: AsyncSession = Depends(get_db),
    user: UserPayload = Depends(require_staff),
):
    """
    Performance metrics for all published posters.

    Joins poster_publications with poster_briefs to get the topic,
    then aggregates reach and engagement across all published posts.
    Returns the top performer (highest reach_24h).
    """
    result = await db.execute(
        select(
            PosterPublication,
            PosterBrief.topic,
        )
        .join(PosterBrief, PosterPublication.brief_id == PosterBrief.id)
        .where(PosterPublication.status == PublicationStatus.PUBLISHED)
        .order_by(PosterPublication.published_at.desc())
    )
    rows = result.all()

    if not rows:
        return PublishedAnalyticsResponse(
            posts=[],
            avg_reach=0.0,
            avg_engagement=0.0,
            top_performer=None,
        )

    posts = [
        PublishedPostSummary(
            publication_id=pub.id,
            brief_id=pub.brief_id,
            topic=topic,
            platform=pub.platform,
            language=pub.language,
            published_at=pub.published_at,
            reach_24h=pub.reach_24h,
            engagements_24h=pub.engagements_24h,
            followers_gained_24h=pub.followers_gained_24h,
        )
        for pub, topic in rows
    ]

    total = len(posts)
    avg_reach = sum(p.reach_24h for p in posts) / total
    avg_engagement = sum(p.engagements_24h for p in posts) / total
    top_performer = max(posts, key=lambda p: p.reach_24h)

    return PublishedAnalyticsResponse(
        posts=posts,
        avg_reach=round(avg_reach, 1),
        avg_engagement=round(avg_engagement, 1),
        top_performer=top_performer,
    )


# ─────────────────────────────────────────────────────────────────────────────
# GET /poster/analytics/quality
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/analytics/quality", response_model=QualityAnalyticsResponse)
async def get_quality_analytics(
    db: AsyncSession = Depends(get_db),
    user: UserPayload = Depends(require_staff),
):
    """
    Review score trends and approval rate.

    Queries poster_reviews to compute:
      - Average score per dimension (brand, clarity, visual, cultural)
      - Overall approval rate (approved reviews / total reviews)
      - Average revision cycles across all briefs
    """
    # Average scores per dimension across all reviews
    score_result = await db.execute(
        select(
            func.avg(cast(PosterReview.score_brand,    Float)).label("avg_brand"),
            func.avg(cast(PosterReview.score_clarity,  Float)).label("avg_clarity"),
            func.avg(cast(PosterReview.score_visual,   Float)).label("avg_visual"),
            func.avg(cast(PosterReview.score_cultural, Float)).label("avg_cultural"),
            func.count(PosterReview.id).label("total_reviews"),
            func.sum(
                # Count 1 for each approved review, 0 for others
                func.cast(
                    PosterReview.decision == ReviewDecision.APPROVED,
                    Float,
                )
            ).label("approved_count"),
        )
    )
    score_row = score_result.one()

    total_reviews = score_row.total_reviews or 0
    approved_count = float(score_row.approved_count or 0)
    approval_rate = (approved_count / total_reviews) if total_reviews > 0 else 0.0

    # Average revision cycles across all briefs that have been through review
    revision_result = await db.execute(
        select(func.avg(cast(PosterBrief.revision_count, Float)))
        .where(PosterBrief.revision_count > 0)
    )
    avg_revisions = revision_result.scalar_one_or_none() or 0.0

    return QualityAnalyticsResponse(
        avg_scores_by_dimension={
            "brand":    round(float(score_row.avg_brand    or 0), 2),
            "clarity":  round(float(score_row.avg_clarity  or 0), 2),
            "visual":   round(float(score_row.avg_visual   or 0), 2),
            "cultural": round(float(score_row.avg_cultural or 0), 2),
        },
        approval_rate=round(approval_rate, 3),
        avg_revision_cycles=round(float(avg_revisions), 2),
    )


# ─────────────────────────────────────────────────────────────────────────────
# GET /poster/analytics/agent-costs
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/analytics/agent-costs", response_model=AgentCostResponse)
async def get_agent_costs(
    user: UserPayload = Depends(require_staff),
):
    """
    LangSmith cost data for the poster agent pipeline.

    Uses per-poster cost estimates from the spec (Section 8.1) until
    real LangSmith API integration is built. These match the spec figures:
      - Brief Parser:  $0.01
      - Copywriter:    $0.02
      - Designer:      $0.02
      - Image Gen:     $0.04
      - QA Agent:      $0.02
      - Publisher:     $0.01
      Total per poster (no revision): ~$0.13
    """
    # Spec §8.1 token estimates per agent — used until LangSmith API is wired
    token_breakdown = {
        "brief_parser": 3500,    # ~3K input + 500 output
        "copywriter":   6000,    # ~5K input + brand examples + 1K output
        "designer":     7000,    # ~6K input + 1K output
        "qa_agent":     4500,    # ~4K input + image check + 500 output
        "publisher":    2200,    # ~2K input + 200 output
    }

    cost_per_poster = 0.13   # spec §8.1 no-revision baseline
    daily_cost = cost_per_poster * 3  # 3 posts/day conservative launch target

    return AgentCostResponse(
        daily_cost_usd=round(daily_cost, 4),
        cost_per_poster=cost_per_poster,
        token_breakdown=token_breakdown,
    )


# ─────────────────────────────────────────────────────────────────────────────
# GET /poster/queue/status
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/queue/status", response_model=QueueStatusResponse)
async def get_queue_status(
    db: AsyncSession = Depends(get_db),
    user: UserPayload = Depends(require_staff),
):
    """
    Live count of posters in each pipeline stage.

    Used by the QueueDashboard component to populate the 5 stat tiles.
    Refreshed every 30 seconds by the frontend.

    published_today counts posts published since midnight Sri Lanka time.
    """
    # Midnight today in Sri Lanka time (UTC+5:30)
    sl_tz = timezone(timedelta(hours=5, minutes=30))
    now_sl = datetime.now(sl_tz)
    midnight_sl = now_sl.replace(hour=0, minute=0, second=0, microsecond=0)
    midnight_utc = midnight_sl.astimezone(timezone.utc)

    # Count briefs per status in a single query using conditional aggregation
    result = await db.execute(
        select(
            func.count(PosterBrief.id).filter(
                PosterBrief.status == PosterStatus.GENERATING
            ).label("generating"),
            func.count(PosterBrief.id).filter(
                PosterBrief.status == PosterStatus.PENDING_REVIEW
            ).label("pending_review"),
            func.count(PosterBrief.id).filter(
                PosterBrief.status == PosterStatus.APPROVED
            ).label("approved"),
            func.count(PosterBrief.id).filter(
                PosterBrief.status == PosterStatus.SCHEDULED
            ).label("scheduled"),
        )
    )
    row = result.one()

    # Count publications that went live today
    published_today_result = await db.execute(
        select(func.count(PosterPublication.id)).where(
            PosterPublication.status == PublicationStatus.PUBLISHED,
            PosterPublication.published_at >= midnight_utc,
        )
    )
    published_today = published_today_result.scalar_one() or 0

    return QueueStatusResponse(
        generating=row.generating or 0,
        pending_review=row.pending_review or 0,
        approved=row.approved or 0,
        scheduled=row.scheduled or 0,
        published_today=published_today,
    )
