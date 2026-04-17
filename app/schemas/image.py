"""
app/schemas/image.py
─────────────────────────────────────────────────────────────────────────────
Pydantic schemas for the image gallery endpoints.
Response shape matches what the Next.js frontend expects (see types.ts).
─────────────────────────────────────────────────────────────────────────────
"""

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field

ImageSourceLiteral = Literal["upload", "generated", "approved", "rejected"]


class ImageInfo(BaseModel):
    image_id: str
    url: str
    filename: str
    created_at: datetime
    size_bytes: int
    source: ImageSourceLiteral
    platform: Optional[str] = None
    caption: Optional[str] = None
    scheduled_time: Optional[datetime] = None


class ApproveImageRequest(BaseModel):
    caption: Optional[str] = None
    platforms: Optional[list[str]] = None
    scheduled_time: Optional[datetime] = None


class ApproveImageResponse(BaseModel):
    image_id: str
    approved_url: str
    message: str
    scheduled_time: Optional[datetime] = None


class RejectImageResponse(BaseModel):
    image_id: str
    message: str


class DeleteImageResponse(BaseModel):
    message: str
