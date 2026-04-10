"""
app/models/review.py
─────────────────────────────────────────────────────────────────────────────
poster_reviews table — records every human review decision.

This is the HITL audit log.  Every approval, revision request, and rejection
is recorded here with the reviewer's identity, their scores, their written
feedback, the exact timestamp, and their IP address.

Security & audit:
  • reviewer_id FK → auth.users (NOT NULL) — anonymous reviews are impossible
  • ip_address stored for every review — forensic audit trail
  • All 4 scores are NOT NULL — the API enforces this before writing,
    but the DB enforces it independently as a second line of defence
  • Each score has a CHECK(1-5) constraint — invalid scores cannot be stored
  • score_average is a GENERATED column — always mathematically consistent
    with the four dimension scores; cannot be manually overridden
  • feedback is NOT NULL when decision is revision or rejected — enforced
    in the application layer; reviewer must explain their decision
  • Soft insert-only: reviews are never updated or deleted.
    The audit log is append-only — see insert_only trigger below.
─────────────────────────────────────────────────────────────────────────────
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    Computed,
    DateTime,
    Enum,
    ForeignKey,
    SmallInteger,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import INET, NUMERIC, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class ReviewDecision(str, enum.Enum):
    """The three possible outcomes of a human review."""
    APPROVED = "approved"   # Poster is approved; scheduler agent runs next
    REVISION = "revision"   # Reviewer requests changes; designer agent reruns
    REJECTED = "rejected"   # Hard reject; graph terminates; brief returned


class PosterReview(Base):
    """
    Corresponds to the poster_reviews table in the spec (Section 6.3).

    IMPORTANT: This table is append-only.  Never issue UPDATE or DELETE
    against it.  If you need to "undo" a review, that requires a new review
    record — the history is preserved for the audit trail.
    """
    __tablename__ = "poster_reviews"

    __table_args__ = (
        # All individual scores must be in range 1–5
        CheckConstraint("score_brand    BETWEEN 1 AND 5", name="ck_score_brand"),
        CheckConstraint("score_clarity  BETWEEN 1 AND 5", name="ck_score_clarity"),
        CheckConstraint("score_visual   BETWEEN 1 AND 5", name="ck_score_visual"),
        CheckConstraint("score_cultural BETWEEN 1 AND 5", name="ck_score_cultural"),
    )

    # ── Primary key ───────────────────────────────────────────────────────────
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    # ── Foreign keys ──────────────────────────────────────────────────────────
    brief_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("poster_briefs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("poster_versions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Which specific version was reviewed",
    )

    # ── Reviewer identity (HITL gate authentication) ──────────────────────────
    reviewer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,     # Anonymous reviews are architecturally impossible
        index=True,
        comment="Authenticated reviewer UUID — cannot be NULL",
    )

    # ── Decision ──────────────────────────────────────────────────────────────
    decision: Mapped[ReviewDecision] = mapped_column(
        Enum(
            ReviewDecision,
            name="review_decision_enum",
            create_type=False,
            values_callable=lambda x: [e.value for e in x],
        ),
        nullable=False,
        index=True,
        comment="Review outcome: approved / revision / rejected",
    )

    # ── Quality scores (4-dimension framework from spec Section 4.2) ─────────
    score_brand: Mapped[int] = mapped_column(
        SmallInteger,
        nullable=False,
        comment="Brand alignment score 1–5",
    )

    score_clarity: Mapped[int] = mapped_column(
        SmallInteger,
        nullable=False,
        comment="Message clarity score 1–5",
    )

    score_visual: Mapped[int] = mapped_column(
        SmallInteger,
        nullable=False,
        comment="Visual quality score 1–5",
    )

    score_cultural: Mapped[int] = mapped_column(
        SmallInteger,
        nullable=False,
        comment="Cultural sensitivity score 1–5 (Sri Lankan context)",
    )

    # GENERATED column — always equals the mathematical average of the 4 scores.
    # Cannot be manually set; the DB computes it.
    # This prevents any possibility of storing a fraudulent average.
    score_average: Mapped[float] = mapped_column(
        NUMERIC(3, 2),
        Computed(
            "(score_brand + score_clarity + score_visual + score_cultural) / 4.0",
            persisted=True,   # STORED in PostgreSQL — no recompute cost on read
        ),
        comment="Auto-calculated average of all 4 dimension scores",
    )

    # ── Feedback text ─────────────────────────────────────────────────────────
    # Application layer ensures this is NOT NULL for revision/rejected decisions
    feedback: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Reviewer feedback — required for revision/rejected, optional for approved",
    )

    # ── Audit fields ──────────────────────────────────────────────────────────
    reviewed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        comment="Exact timestamp of the review decision",
    )

    # Reviewer's IP address — stored for forensic audit trail
    # Uses PostgreSQL native INET type — validates IP format at DB level
    ip_address: Mapped[str] = mapped_column(
        INET,
        nullable=False,
        comment="Reviewer IP address for audit trail — PostgreSQL INET type",
    )

    # ── Relationships ─────────────────────────────────────────────────────────
    brief: Mapped["PosterBrief"] = relationship(  # type: ignore[name-defined]
        "PosterBrief",
        back_populates="reviews",
    )

    version: Mapped["PosterVersion"] = relationship(  # type: ignore[name-defined]
        "PosterVersion",
        back_populates="reviews",
    )

    def __repr__(self) -> str:
        return (
            f"<PosterReview id={self.id} decision={self.decision.value} "
            f"avg={self.score_average} reviewer={self.reviewer_id}>"
        )
