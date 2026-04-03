"""
app/schemas/brief.py
─────────────────────────────────────────────────────────────────────────────
Pydantic schemas for brief submission and response.

Why schemas are separate from models:
  SQLAlchemy models  → map to DB columns (internal, raw)
  Pydantic schemas   → define what the API exposes (external, validated)

  This means: you can change DB internals without breaking the API contract,
  and you never accidentally leak internal fields like submitted_by or thread_id.
─────────────────────────────────────────────────────────────────────────────
"""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


# ─────────────────────────────────────────────────────────────────────────────
# Request schemas — what the API accepts
# ─────────────────────────────────────────────────────────────────────────────

class BriefCreate(BaseModel):
    """
    Payload for POST /poster/briefs.
    Validated before the DB row is created or the pipeline starts.
    """

    topic: str = Field(
        min_length=3,
        max_length=200,
        description="Campaign topic, e.g. 'Grand Opening of RISE Tech Village'",
    )

    platforms: list[Literal["instagram", "facebook", "linkedin", "tiktok"]] = Field(
        min_length=1,
        description="One or more target platforms",
    )

    languages: list[Literal["en", "si", "ta"]] = Field(
        min_length=1,
        description="Language codes: en=English, si=Sinhala, ta=Tamil",
    )

    audience: str = Field(
        min_length=2,
        max_length=100,
        description="Target audience segment, e.g. 'Sri Lankan tech professionals 25-40'",
    )

    tone: str = Field(
        min_length=2,
        max_length=60,
        description="Content tone, e.g. 'aspirational', 'professional', 'energetic'",
    )

    key_message: str = Field(
        min_length=10,
        description="Core message the poster must communicate",
    )

    brand_notes: str | None = Field(
        default=None,
        description="Optional special brand instructions for this brief",
    )

    @field_validator("platforms")
    @classmethod
    def no_duplicate_platforms(cls, v: list) -> list:
        if len(v) != len(set(v)):
            raise ValueError("platforms list must not contain duplicates")
        return v

    @field_validator("languages")
    @classmethod
    def no_duplicate_languages(cls, v: list) -> list:
        if len(v) != len(set(v)):
            raise ValueError("languages list must not contain duplicates")
        return v


# ─────────────────────────────────────────────────────────────────────────────
# Response schemas — what the API returns
# ─────────────────────────────────────────────────────────────────────────────

class BriefSubmitResponse(BaseModel):
    """
    Returned immediately after POST /poster/briefs.
    The pipeline is starting in the background — client polls GET /briefs/{id}.
    """
    brief_id: UUID
    thread_id: str
    status: str
    eta_seconds: int = Field(
        default=90,
        description="Estimated seconds until poster reaches pending_review",
    )


class BriefDetail(BaseModel):
    """
    Returned by GET /poster/briefs/{brief_id}.
    Full brief data plus current pipeline position.
    """
    brief_id: UUID
    thread_id: str
    topic: str
    platforms: list[str]
    languages: list[str]
    audience: str
    tone: str
    key_message: str
    brand_notes: str | None
    status: str
    revision_count: int
    created_at: datetime
    current_node: str | None     # which LangGraph node is active / next
    qa_confidence: float | None  # latest QA confidence score


class BriefListItem(BaseModel):
    """
    One item in the list returned by GET /poster/briefs.
    Lighter than BriefDetail — no pipeline internals.
    """
    brief_id: UUID
    topic: str
    platforms: list[str]
    languages: list[str]
    status: str
    revision_count: int
    created_at: datetime


class BriefListResponse(BaseModel):
    """Paginated list of briefs."""
    briefs: list[BriefListItem]
    total: int
    page: int


class BriefCancelResponse(BaseModel):
    """Returned by DELETE /poster/briefs/{brief_id}."""
    cancelled: bool
