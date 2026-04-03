"""
app/models/publication.py
─────────────────────────────────────────────────────────────────────────────
poster_publications table — records every platform publish action.

One approved poster version generates one publication record per
platform × language combination.  Example: an approved Instagram + Facebook
brief in English + Sinhala creates 4 publication records.

Post-publish, the Scheduler Agent populates the analytics columns after
24 hours by querying each platform's analytics API.
─────────────────────────────────────────────────────────────────────────────
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class PublicationStatus(str, enum.Enum):
    """Status of a single platform publish action."""
    SCHEDULED  = "scheduled"    # Queued; publish time set
    PUBLISHED  = "published"    # Successfully posted; external_post_id recorded
    FAILED     = "failed"       # Publish attempt failed; retry logic handles


class PosterPublication(Base):
    """
    Corresponds to the poster_publications table in the spec (Section 6.4).
    """
    __tablename__ = "poster_publications"

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
        comment="Which approved version was published",
    )

    # ── Publication target ────────────────────────────────────────────────────
    platform: Mapped[str] = mapped_column(
        String(40),
        nullable=False,
        index=True,
        comment="Target platform: instagram / facebook / linkedin / tiktok",
    )

    language: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
        comment="Language variant published: en / si / ta",
    )

    # ── Platform response ─────────────────────────────────────────────────────
    # Stored after successful publish — used to fetch analytics later
    external_post_id: Mapped[str | None] = mapped_column(
        String(200),
        nullable=True,
        comment="Platform-returned post ID — populated after successful publish",
    )

    # ── Schedule ──────────────────────────────────────────────────────────────
    scheduled_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        comment="Scheduled publish time (Sri Lanka optimal hours from config)",
    )

    published_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Actual confirmation time from platform API",
    )

    # ── Status ────────────────────────────────────────────────────────────────
    status: Mapped[PublicationStatus] = mapped_column(
        Enum(PublicationStatus, name="publication_status_enum", create_type=True),
        nullable=False,
        default=PublicationStatus.SCHEDULED,
        index=True,
    )

    # ── 24-hour analytics (populated by Scheduler Agent after publish) ────────
    reach_24h: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="Total reach 24 hours after publish",
    )

    engagements_24h: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="Total engagements (likes + comments + shares) at 24h",
    )

    followers_gained_24h: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="Net new followers gained in 24h after this post",
    )

    analytics_fetched_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="When 24h analytics were fetched from the platform API",
    )

    # ── Audit ─────────────────────────────────────────────────────────────────
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    # ── Relationships ─────────────────────────────────────────────────────────
    brief: Mapped["PosterBrief"] = relationship(  # type: ignore[name-defined]
        "PosterBrief",
        back_populates="publications",
    )

    version: Mapped["PosterVersion"] = relationship(  # type: ignore[name-defined]
        "PosterVersion",
        back_populates="publications",
    )

    def __repr__(self) -> str:
        return (
            f"<PosterPublication id={self.id} platform={self.platform} "
            f"lang={self.language} status={self.status.value}>"
        )
