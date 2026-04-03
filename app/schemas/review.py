"""
app/schemas/review.py
─────────────────────────────────────────────────────────────────────────────
Pydantic schemas for the HITL review endpoints.

Validation happens here BEFORE the DB is touched or the graph is resumed.
If the scores don't pass, the request is rejected with 422 — nothing writes.
─────────────────────────────────────────────────────────────────────────────
"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

from app.config import settings


# ─────────────────────────────────────────────────────────────────────────────
# Scores — shared by all three review actions
# ─────────────────────────────────────────────────────────────────────────────

class ReviewScores(BaseModel):
    """
    Four-dimension quality scoring framework from spec §4.2.
    Each score is 1–5. A score of 1 on ANY dimension is a critical failure.
    """
    brand:    int = Field(ge=1, le=5, description="Brand alignment 1–5")
    clarity:  int = Field(ge=1, le=5, description="Message clarity 1–5")
    visual:   int = Field(ge=1, le=5, description="Visual quality 1–5")
    cultural: int = Field(ge=1, le=5, description="Cultural sensitivity 1–5")

    @property
    def average(self) -> float:
        return (self.brand + self.clarity + self.visual + self.cultural) / 4.0

    @property
    def has_critical_failure(self) -> bool:
        """Any single score of 1 is a critical failure — blocks approval."""
        return any(s == 1 for s in [self.brand, self.clarity, self.visual, self.cultural])


# ─────────────────────────────────────────────────────────────────────────────
# Request schemas — one per review action
# ─────────────────────────────────────────────────────────────────────────────

class ApproveRequest(BaseModel):
    """
    POST /poster/review/{brief_id}/approve

    Validation rules (from spec §4.2 Score Threshold Logic):
      - All 4 scores must be provided (enforced by ReviewScores)
      - No individual score can be 1 (critical failure)
      - Average must be >= REVIEW_APPROVAL_MIN_SCORE (default 3.5)
    """
    scores: ReviewScores
    feedback: str | None = Field(
        default=None,
        description="Optional note — why this poster is approved",
    )
    schedule_override: datetime | None = Field(
        default=None,
        description="Override default publish time. Must be a future datetime.",
    )

    @model_validator(mode="after")
    def validate_approval_scores(self) -> "ApproveRequest":
        if self.scores.has_critical_failure:
            raise ValueError(
                "Approval blocked: one or more scores are 1 (critical failure). "
                "Request a revision or reject instead."
            )
        if self.scores.average < settings.REVIEW_APPROVAL_MIN_SCORE:
            raise ValueError(
                f"Approval blocked: average score {self.scores.average:.2f} is below "
                f"the minimum required {settings.REVIEW_APPROVAL_MIN_SCORE}. "
                "Request a revision to improve the poster."
            )
        return self


class ReviseRequest(BaseModel):
    """
    POST /poster/review/{brief_id}/revise

    feedback is REQUIRED — the designer agent uses it as hard constraints
    for the next generation cycle.
    """
    scores: ReviewScores
    feedback: str = Field(
        min_length=10,
        description="Required: specific instructions for the designer agent to fix",
    )


class RejectRequest(BaseModel):
    """
    POST /poster/review/{brief_id}/reject

    Hard reject — terminates the graph. Brief is returned to coordinator.
    reject_reason is stored in the audit log.
    """
    scores: ReviewScores
    reject_reason: str = Field(
        min_length=10,
        description="Required: reason for rejection — stored in audit log",
    )


# ─────────────────────────────────────────────────────────────────────────────
# Response schemas
# ─────────────────────────────────────────────────────────────────────────────

class ReviewQueueItem(BaseModel):
    """One poster in the pending review queue."""
    brief_id: UUID
    topic: str
    platforms: list[str]
    languages: list[str]
    created_at: datetime
    revision_count: int
    qa_confidence: float | None
    poster_url: str | None       # presigned CloudFront URL for thumbnail preview


class ReviewQueueResponse(BaseModel):
    """Returned by GET /poster/review/queue."""
    posters: list[ReviewQueueItem]
    count: int
    oldest_pending_age_hours: float | None


class VersionHistoryItem(BaseModel):
    """One entry in the version history panel of the review interface."""
    version_number: int
    created_at: datetime
    qa_confidence: float
    qa_report: dict
    poster_urls: dict
    review_decision: str | None   # approved / revision / rejected / None if not yet reviewed
    review_feedback: str | None


class ReviewDetailResponse(BaseModel):
    """Returned by GET /poster/review/{brief_id}."""
    brief_id: UUID
    topic: str
    platforms: list[str]
    languages: list[str]
    audience: str
    tone: str
    key_message: str
    brand_notes: str | None
    revision_count: int
    poster_urls: dict            # current version's platform-sized URLs
    qa_report: dict              # current version's QA report
    qa_confidence: float
    version_history: list[VersionHistoryItem]


class ApproveResponse(BaseModel):
    approved: bool
    scheduled_at: dict           # { "instagram": "2026-03-29T14:30:00Z", ... }


class ReviseResponse(BaseModel):
    revision_number: int
    regenerating: bool
    eta_seconds: int = 90


class RejectResponse(BaseModel):
    rejected: bool
    brief_returned: bool
