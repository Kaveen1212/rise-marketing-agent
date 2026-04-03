"""
app/schemas/analytics.py
─────────────────────────────────────────────────────────────────────────────
Pydantic schemas for analytics and monitoring response payloads.
Used by GET /poster/analytics/* and GET /poster/queue/status
─────────────────────────────────────────────────────────────────────────────
"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


# ─────────────────────────────────────────────────────────────────────────────
# Published post analytics
# ─────────────────────────────────────────────────────────────────────────────

class PublishedPostSummary(BaseModel):
    """One published post with its 24h engagement metrics."""
    publication_id: UUID
    brief_id: UUID
    topic: str
    platform: str
    language: str
    published_at: datetime | None
    reach_24h: int
    engagements_24h: int
    followers_gained_24h: int


class PublishedAnalyticsResponse(BaseModel):
    """Returned by GET /poster/analytics/published"""
    posts: list[PublishedPostSummary]
    avg_reach: float
    avg_engagement: float
    top_performer: PublishedPostSummary | None


# ─────────────────────────────────────────────────────────────────────────────
# Quality / review analytics
# ─────────────────────────────────────────────────────────────────────────────

class QualityAnalyticsResponse(BaseModel):
    """Returned by GET /poster/analytics/quality"""
    avg_scores_by_dimension: dict   # {"brand": 4.2, "clarity": 3.9, "visual": 4.1, "cultural": 4.4}
    approval_rate: float            # 0.0 – 1.0  (approved / total reviews)
    avg_revision_cycles: float      # average revision_count across all briefs


# ─────────────────────────────────────────────────────────────────────────────
# Agent cost analytics (LangSmith)
# ─────────────────────────────────────────────────────────────────────────────

class AgentCostResponse(BaseModel):
    """Returned by GET /poster/analytics/agent-costs"""
    daily_cost_usd: float
    cost_per_poster: float
    token_breakdown: dict   # {"brief_parser": 3000, "copywriter": 5000, ...}
    note: str = "Live LangSmith data — costs update with each pipeline run"


# ─────────────────────────────────────────────────────────────────────────────
# Queue status (live pipeline counts)
# ─────────────────────────────────────────────────────────────────────────────

class QueueStatusResponse(BaseModel):
    """Returned by GET /poster/queue/status — used by QueueDashboard component"""
    generating: int
    pending_review: int
    approved: int
    scheduled: int
    published_today: int
