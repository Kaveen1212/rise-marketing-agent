"""
app/schemas/chat.py
─────────────────────────────────────────────────────────────────────────────
Pydantic schemas for the chat-based brief UI.
Response shape matches what the Next.js frontend expects (see types.ts).
─────────────────────────────────────────────────────────────────────────────
"""

from typing import Literal, Optional

from pydantic import BaseModel, Field

ChatStatus = Literal["ready", "needs_clarification", "generating", "done", "chat"]


class BriefSummary(BaseModel):
    topic: Optional[str] = None
    audience: Optional[str] = None
    tone: Optional[str] = None
    key_message: Optional[str] = None
    caption: Optional[str] = None
    platforms: Optional[list[str]] = None


class ChatMessageRequest(BaseModel):
    message: str = Field(min_length=1)
    session_id: Optional[str] = None


class ChatGenerateRequest(BaseModel):
    prompt: str = Field(min_length=1)
    platform: str = "instagram"
    style: str = "professional"


class ChatResponse(BaseModel):
    session_id: str
    message: str
    status: ChatStatus = "chat"
    image_url: Optional[str] = None
    image_id: Optional[str] = None
    brief: Optional[BriefSummary] = None
    suggested_post_time: Optional[str] = None
    platforms: Optional[list[str]] = None


class ChatHistoryMessage(BaseModel):
    role: str
    content: str
    image_url: Optional[str] = None
    image_id: Optional[str] = None


class ChatHistoryResponse(BaseModel):
    session_id: str
    messages: list[ChatHistoryMessage]
    brief: Optional[BriefSummary] = None


class ChatSessionSummary(BaseModel):
    session_id: str
    title: str
    status: ChatStatus
    created_at: str
    updated_at: str
    message_count: int


class ChatSessionListResponse(BaseModel):
    sessions: list[ChatSessionSummary]
