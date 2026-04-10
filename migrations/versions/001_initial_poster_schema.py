"""Initial poster agent schema — all 4 tables

Revision ID: 001_initial
Revises:
Create Date: 2026-03-27

Creates:
  - poster_status_enum        (PostgreSQL native ENUM)
  - review_decision_enum      (PostgreSQL native ENUM)
  - publication_status_enum   (PostgreSQL native ENUM)
  - poster_briefs             (root entity)
  - poster_versions           (AI-generated content per revision)
  - poster_reviews            (HITL audit log — append only)
  - poster_publications       (platform publish records + 24h analytics)

Security notes:
  - UUID primary keys throughout (no sequential integer IDs)
  - All FK constraints with appropriate ON DELETE rules
  - CHECK constraints enforce business rules at DB level
  - score_average is a GENERATED (stored) column — cannot be falsified
  - ip_address uses PostgreSQL INET type (validates IP format)
  - revision_count CHECK <= 3 enforces the spec's hard limit
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:

    # ── ENUM types (check existence before creating — PG < 16 has no IF NOT EXISTS for TYPE)
    op.execute("""
        DO $$ BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'poster_status_enum') THEN
                CREATE TYPE poster_status_enum AS ENUM ('generating', 'qa_check', 'pending_review', 'in_revision', 'approved', 'scheduled', 'published', 'rejected', 'exhausted');
            END IF;
        END $$;
    """)
    op.execute("""
        DO $$ BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'review_decision_enum') THEN
                CREATE TYPE review_decision_enum AS ENUM ('approved', 'revision', 'rejected');
            END IF;
        END $$;
    """)
    op.execute("""
        DO $$ BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'publication_status_enum') THEN
                CREATE TYPE publication_status_enum AS ENUM ('scheduled', 'published', 'failed');
            END IF;
        END $$;
    """)

    # ── poster_briefs ─────────────────────────────────────────────────────────
    op.create_table(
        "poster_briefs",
        # UUID PK — prevents sequential ID enumeration attacks
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
            comment="Brief identifier — UUID prevents enumeration attacks",
        ),
        sa.Column(
            "thread_id",
            sa.String(100),
            nullable=False,
            comment="LangGraph thread_id — links this row to the checkpointed graph state",
        ),
        sa.Column(
            "submitted_by",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            comment="Submitting user UUID — matches API key identity",
        ),
        sa.Column("topic",            sa.String(200), nullable=False),
        sa.Column("platforms",        postgresql.ARRAY(sa.Text()), nullable=False),
        sa.Column("languages",        postgresql.ARRAY(sa.Text()), nullable=False),
        sa.Column("audience_segment", sa.String(100), nullable=False),
        sa.Column("tone",             sa.String(60),  nullable=False),
        sa.Column("key_message",      sa.Text(),      nullable=False),
        sa.Column("brand_notes",      sa.Text(),      nullable=True),
        sa.Column(
            "status",
            postgresql.ENUM(
                "generating", "qa_check", "pending_review", "in_revision",
                "approved", "scheduled", "published", "rejected", "exhausted",
                name="poster_status_enum",
                create_type=False,
            ),
            nullable=False,
            server_default="generating",
        ),
        sa.Column(
            "revision_count",
            sa.SmallInteger(),
            nullable=False,
            server_default="0",
            comment="Number of revision cycles — hard max 3 enforced by CHECK",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),

        # Table-level constraints
        sa.CheckConstraint(
            "revision_count >= 0 AND revision_count <= 3",
            name="ck_revision_count",
        ),
        sa.UniqueConstraint("thread_id", name="uq_thread_id"),
    )
    op.create_index("ix_poster_briefs_status",       "poster_briefs", ["status"])
    op.create_index("ix_poster_briefs_submitted_by", "poster_briefs", ["submitted_by"])
    op.create_index("ix_poster_briefs_thread_id",    "poster_briefs", ["thread_id"], unique=True)

    # ── poster_versions ───────────────────────────────────────────────────────
    op.create_table(
        "poster_versions",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "brief_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("poster_briefs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("version_number", sa.SmallInteger(), nullable=False),
        # JSONB columns — multilingual copy
        sa.Column("headline",        postgresql.JSONB(), nullable=False),
        sa.Column("body_copy",       postgresql.JSONB(), nullable=False),
        sa.Column("cta",             postgresql.JSONB(), nullable=False),
        sa.Column("hashtags",        postgresql.JSONB(), nullable=False),
        # Visual design
        sa.Column("image_prompt",    sa.Text(), nullable=False),
        sa.Column(
            "image_url",
            sa.Text(),
            nullable=False,
            comment="Private S3 path — NOT a public URL",
        ),
        sa.Column("poster_urls",     postgresql.JSONB(), nullable=False),
        sa.Column("design_manifest", postgresql.JSONB(), nullable=False),
        # QA results
        sa.Column("qa_report",       postgresql.JSONB(), nullable=False),
        sa.Column(
            "qa_confidence",
            sa.Numeric(4, 3),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        # Constraints
        sa.CheckConstraint(
            "version_number >= 1 AND version_number <= 3",
            name="ck_version_number_range",
        ),
        sa.CheckConstraint(
            "qa_confidence >= 0.000 AND qa_confidence <= 1.000",
            name="ck_qa_confidence_range",
        ),
    )
    op.create_index("ix_poster_versions_brief_id", "poster_versions", ["brief_id"])

    # ── poster_reviews ────────────────────────────────────────────────────────
    op.create_table(
        "poster_reviews",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "brief_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("poster_briefs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "version_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("poster_versions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        # NOT NULL — anonymous reviews are impossible
        sa.Column(
            "reviewer_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            comment="Authenticated reviewer UUID — cannot be NULL",
        ),
        sa.Column(
            "decision",
            postgresql.ENUM(
                "approved", "revision", "rejected",
                name="review_decision_enum",
                create_type=False,
            ),
            nullable=False,
        ),
        # Individual scores — all NOT NULL, all CHECK(1-5)
        sa.Column("score_brand",    sa.SmallInteger(), nullable=False),
        sa.Column("score_clarity",  sa.SmallInteger(), nullable=False),
        sa.Column("score_visual",   sa.SmallInteger(), nullable=False),
        sa.Column("score_cultural", sa.SmallInteger(), nullable=False),
        # GENERATED STORED column — mathematically guaranteed average
        sa.Column(
            "score_average",
            sa.Numeric(3, 2),
            sa.Computed(
                "(score_brand + score_clarity + score_visual + score_cultural) / 4.0",
                persisted=True,
            ),
            comment="Auto-calculated average — GENERATED STORED, cannot be falsified",
        ),
        sa.Column("feedback",    sa.Text(), nullable=True),
        sa.Column(
            "reviewed_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        # PostgreSQL INET type — validates IP address format at DB level
        sa.Column(
            "ip_address",
            postgresql.INET(),
            nullable=False,
            comment="Reviewer IP for forensic audit trail",
        ),
        # CHECK constraints on individual scores
        sa.CheckConstraint("score_brand    BETWEEN 1 AND 5", name="ck_score_brand"),
        sa.CheckConstraint("score_clarity  BETWEEN 1 AND 5", name="ck_score_clarity"),
        sa.CheckConstraint("score_visual   BETWEEN 1 AND 5", name="ck_score_visual"),
        sa.CheckConstraint("score_cultural BETWEEN 1 AND 5", name="ck_score_cultural"),
    )
    op.create_index("ix_poster_reviews_brief_id",   "poster_reviews", ["brief_id"])
    op.create_index("ix_poster_reviews_version_id", "poster_reviews", ["version_id"])
    op.create_index("ix_poster_reviews_reviewer_id","poster_reviews", ["reviewer_id"])
    op.create_index("ix_poster_reviews_decision",   "poster_reviews", ["decision"])

    # ── poster_publications ───────────────────────────────────────────────────
    op.create_table(
        "poster_publications",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "brief_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("poster_briefs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "version_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("poster_versions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("platform",         sa.String(40),              nullable=False),
        sa.Column("language",         sa.String(10),              nullable=False),
        sa.Column("external_post_id", sa.String(200),             nullable=True),
        sa.Column("scheduled_at",     sa.DateTime(timezone=True), nullable=False),
        sa.Column("published_at",     sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "status",
            postgresql.ENUM(
                "scheduled", "published", "failed",
                name="publication_status_enum",
                create_type=False,
            ),
            nullable=False,
            server_default="scheduled",
        ),
        # 24-hour analytics — populated by Scheduler Agent after publish
        sa.Column("reach_24h",            sa.Integer(), nullable=False, server_default="0"),
        sa.Column("engagements_24h",      sa.Integer(), nullable=False, server_default="0"),
        sa.Column("followers_gained_24h", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("analytics_fetched_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("ix_poster_publications_brief_id",  "poster_publications", ["brief_id"])
    op.create_index("ix_poster_publications_version_id","poster_publications", ["version_id"])
    op.create_index("ix_poster_publications_platform",  "poster_publications", ["platform"])
    op.create_index("ix_poster_publications_status",    "poster_publications", ["status"])


def downgrade() -> None:
    # Drop tables in reverse order (FK dependencies)
    op.drop_table("poster_publications")
    op.drop_table("poster_reviews")
    op.drop_table("poster_versions")
    op.drop_table("poster_briefs")

    # Drop ENUM types after tables
    op.execute("DROP TYPE IF EXISTS publication_status_enum")
    op.execute("DROP TYPE IF EXISTS review_decision_enum")
    op.execute("DROP TYPE IF EXISTS poster_status_enum")
