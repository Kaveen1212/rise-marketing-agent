"""
app/models/version.py
─────────────────────────────────────────────────────────────────────────────
poster_versions table — stores every AI-generated poster version.

Each brief can have up to 3 versions (one per revision cycle).
The version stores all generated content: multilingual copy, image URLs,
design manifest, and the QA Agent's automated check results.

Security:
  • image_url and poster_urls point to private S3 — CloudFront signed URLs
    are generated on-demand with 1h expiry; raw S3 URLs are never exposed
  • qa_report and design_manifest are JSONB — schema-validated in the
    application layer before storage
  • version_number CHECK 1-3 enforced at DB level
─────────────────────────────────────────────────────────────────────────────
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    SmallInteger,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, NUMERIC, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class PosterVersion(Base):
    """
    Corresponds to the poster_versions table in the spec (Section 6.2).
    """
    __tablename__ = "poster_versions"

    __table_args__ = (
        # Version numbers must be 1, 2, or 3
        CheckConstraint(
            "version_number >= 1 AND version_number <= 3",
            name="ck_version_number_range",
        ),
        # QA confidence must be a valid probability
        CheckConstraint(
            "qa_confidence >= 0.000 AND qa_confidence <= 1.000",
            name="ck_qa_confidence_range",
        ),
    )

    # ── Primary key ───────────────────────────────────────────────────────────
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    # ── Parent brief ──────────────────────────────────────────────────────────
    brief_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("poster_briefs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Parent brief — CASCADE delete if brief is deleted",
    )

    version_number: Mapped[int] = mapped_column(
        SmallInteger,
        nullable=False,
        comment="1, 2, or 3 — max enforced by CHECK constraint",
    )

    # ── Multilingual copy (Agent 2 output) ───────────────────────────────────
    # JSONB structure: { "en": "...", "si": "...", "ta": "..." }
    headline: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        comment='Multilingual headlines: {"en": "...", "si": "...", "ta": "..."}',
    )

    body_copy: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        comment="Multilingual body copy",
    )

    cta: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        comment="Multilingual call-to-action text",
    )

    hashtags: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        comment='Per-platform hashtag sets: {"instagram": [...], "facebook": [...]}',
    )

    # ── Visual design (Agent 3 output) ───────────────────────────────────────
    image_prompt: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="Prompt sent to Stability AI / DALL-E 3 for image generation",
    )

    # Private S3 path — never the CloudFront URL (that is generated on-demand)
    image_url: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="Private S3 path to base generated image — NOT a public URL",
    )

    # JSONB: { "instagram": "s3://...", "facebook": "s3://...", ... }
    poster_urls: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        comment="Private S3 paths to platform-sized poster variants",
    )

    # JSONB: template id, palette hex codes, font names, layout spec
    design_manifest: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        comment="Full design spec: template, palette, fonts, layout",
    )

    # ── QA check results (Agent 4 output) ────────────────────────────────────
    # JSONB: { "brand_colours": true, "logo_placement": true, "contrast_ratio": false, ... }
    qa_report: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        comment="Per-check pass/fail results from QA Agent",
    )

    qa_confidence: Mapped[float] = mapped_column(
        NUMERIC(4, 3),   # e.g. 0.873 — 3 decimal places precision
        nullable=False,
        comment="Overall QA confidence score 0.000–1.000",
    )

    # ── Audit ────────────────────────────────────────────────────────────────
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    # ── Relationships ─────────────────────────────────────────────────────────
    brief: Mapped["PosterBrief"] = relationship(  # type: ignore[name-defined]
        "PosterBrief",
        back_populates="versions",
    )

    reviews: Mapped[list["PosterReview"]] = relationship(  # type: ignore[name-defined]
        "PosterReview",
        back_populates="version",
        cascade="all, delete-orphan",
        lazy="select",
    )

    publications: Mapped[list["PosterPublication"]] = relationship(  # type: ignore[name-defined]
        "PosterPublication",
        back_populates="version",
        cascade="all, delete-orphan",
        lazy="select",
    )

    def __repr__(self) -> str:
        return (
            f"<PosterVersion id={self.id} brief={self.brief_id} "
            f"v={self.version_number} qa={self.qa_confidence}>"
        )
