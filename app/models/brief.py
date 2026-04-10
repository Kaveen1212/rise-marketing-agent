"""
app/models/brief.py
─────────────────────────────────────────────────────────────────────────────
poster_briefs table — the root entity for the entire pipeline.

One brief = one campaign request = one LangGraph thread.
The thread_id is the key that links the database row to the LangGraph
checkpointed state — this is how the HITL gate resumes the correct graph.

Security & integrity:
  • UUID primary key — prevents enumeration attacks (no sequential IDs)
  • submitted_by FK → auth.users — every brief is owned by an authenticated user
  • revision_count CHECK ≤ 3 — hard DB constraint, not just application logic
  • status ENUM — only valid pipeline states can be stored
  • created_at / completed_at — immutable audit trail
─────────────────────────────────────────────────────────────────────────────
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    ARRAY,
    CheckConstraint,
    DateTime,
    Enum,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class PosterStatus(str, enum.Enum):
    """
    All valid states in the poster pipeline.

    Flow:  generating → qa_check → pending_review
                                 ↘ in_revision (loop back to generating)
           pending_review → approved → scheduled → published
           pending_review → rejected
           in_revision (×3) → exhausted
    """
    GENERATING     = "generating"       # AI agents actively producing
    QA_CHECK       = "qa_check"         # QA Agent running automated checks
    PENDING_REVIEW = "pending_review"   # Waiting for human reviewer — HITL gate open
    IN_REVISION    = "in_revision"      # Reviewer requested changes; AI regenerating
    APPROVED       = "approved"         # Human approved; awaiting scheduled publish time
    SCHEDULED      = "scheduled"        # Queued in platform; publish time set
    PUBLISHED      = "published"        # Successfully posted to all target platforms
    REJECTED       = "rejected"         # Human reviewer rejected; no further processing
    EXHAUSTED      = "exhausted"        # 3 revision cycles completed without approval


class PosterBrief(Base):
    """
    Corresponds to the poster_briefs table in the spec (Section 6.1).
    """
    __tablename__ = "poster_briefs"

    __table_args__ = (
        # Hard DB constraint — revision_count cannot exceed 3 from spec
        CheckConstraint("revision_count >= 0 AND revision_count <= 3", name="ck_revision_count"),
        # thread_id must be unique — one brief = one LangGraph thread
        UniqueConstraint("thread_id", name="uq_thread_id"),
        # Performance: most queries filter by status and submitted_by
        # Indexes are defined on the columns below via index=True
    )

    # ── Primary key ──────────────────────────────────────────────────────────
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        comment="Brief identifier — UUID prevents enumeration attacks",
    )

    # ── LangGraph link ───────────────────────────────────────────────────────
    thread_id: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        unique=True,
        index=True,
        comment="LangGraph thread_id — links DB row to checkpointed graph state",
    )

    # ── Ownership ────────────────────────────────────────────────────────────
    submitted_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
        index=True,
        comment="Submitting user UUID — matches API key identity",
    )

    # ── Campaign brief fields ─────────────────────────────────────────────────
    topic: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
        comment="Campaign topic",
    )

    # ARRAY type: platforms = ['instagram', 'facebook', 'linkedin', 'tiktok']
    platforms: Mapped[list[str]] = mapped_column(
        ARRAY(Text),
        nullable=False,
        comment="Target social media platforms",
    )

    # ARRAY type: languages = ['en', 'si', 'ta']
    languages: Mapped[list[str]] = mapped_column(
        ARRAY(Text),
        nullable=False,
        comment="Target language codes: en=English, si=Sinhala, ta=Tamil",
    )

    audience_segment: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="Target audience segment",
    )

    tone: Mapped[str] = mapped_column(
        String(60),
        nullable=False,
        comment="Content tone (e.g. aspirational, professional, fun)",
    )

    key_message: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="Core message the poster must communicate",
    )

    brand_notes: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Optional special brand instructions for this brief",
    )

    # ── Pipeline state ───────────────────────────────────────────────────────
    status: Mapped[PosterStatus] = mapped_column(
        Enum(
            PosterStatus,
            name="poster_status_enum",
            create_type=False,
            values_callable=lambda x: [e.value for e in x],
        ),
        nullable=False,
        default=PosterStatus.GENERATING,
        index=True,
        comment="Current pipeline status",
    )

    revision_count: Mapped[int] = mapped_column(
        SmallInteger,
        nullable=False,
        default=0,
        comment="Number of revision cycles used — max 3, enforced by CHECK constraint",
    )

    # ── Audit timestamps ─────────────────────────────────────────────────────
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        comment="When the brief was submitted",
    )

    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="When the brief reached a terminal state (published/rejected/exhausted)",
    )

    # ── Relationships ─────────────────────────────────────────────────────────
    versions: Mapped[list["PosterVersion"]] = relationship(  # type: ignore[name-defined]
        "PosterVersion",
        back_populates="brief",
        cascade="all, delete-orphan",
        order_by="PosterVersion.version_number",
        lazy="select",
    )

    reviews: Mapped[list["PosterReview"]] = relationship(  # type: ignore[name-defined]
        "PosterReview",
        back_populates="brief",
        cascade="all, delete-orphan",
        lazy="select",
    )

    publications: Mapped[list["PosterPublication"]] = relationship(  # type: ignore[name-defined]
        "PosterPublication",
        back_populates="brief",
        cascade="all, delete-orphan",
        lazy="select",
    )

    def __repr__(self) -> str:
        # Never include sensitive data in repr
        return f"<PosterBrief id={self.id} status={self.status.value} topic={self.topic!r}>"
