"""
app/api/chat.py
─────────────────────────────────────────────────────────────────────────────
Chat endpoints for the conversational brief UI.

Routes:
  POST /poster/chat/message           → send a message, get AI reply
  POST /poster/chat/generate          → generate a poster image from a prompt
  GET  /poster/chat/history/{id}      → full message history for a session
─────────────────────────────────────────────────────────────────────────────
"""

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.schemas.chat import (
    BriefSummary,
    ChatGenerateRequest,
    ChatHistoryMessage,
    ChatHistoryResponse,
    ChatMessageRequest,
    ChatResponse,
    ChatSessionListResponse,
    ChatSessionSummary,
)
from app.services import chat_service, image_service

log = structlog.get_logger()

router = APIRouter()


def _request_base(request: Request) -> str:
    proto = request.headers.get("x-forwarded-proto", request.url.scheme)
    host = request.headers.get("x-forwarded-host") or request.headers.get("host") or request.url.netloc
    return f"{proto}://{host}"


def _absolutize(url: str | None, base: str) -> str | None:
    if not url:
        return url
    if url.startswith("/"):
        return f"{base}{url}"
    return url


@router.post("/chat/message", response_model=ChatResponse)
async def send_chat_message(
    body: ChatMessageRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    base = _request_base(request)
    result = await chat_service.process_chat_message(
        db=db,
        user_message=body.message,
        session_id=body.session_id,
        request_base=base,
    )
    result["image_url"] = _absolutize(result.get("image_url"), base)
    return ChatResponse(**result)


@router.post("/chat/generate", response_model=ChatResponse)
async def generate_poster(
    body: ChatGenerateRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    base = _request_base(request)
    image = await image_service.generate_image(
        db=db,
        prompt=body.prompt,
        platform=body.platform,
        session_id=None,
        request_base=base,
    )
    return ChatResponse(
        session_id=str(image.id),
        message="Generated a poster preview. Review and approve when ready.",
        status="ready",
        image_url=_absolutize(image.url, base),
        image_id=str(image.id),
    )


@router.get("/chat/sessions", response_model=ChatSessionListResponse)
async def list_chat_sessions(
    db: AsyncSession = Depends(get_db),
):
    sessions = await chat_service.list_sessions(db)
    return ChatSessionListResponse(
        sessions=[ChatSessionSummary(**s) for s in sessions],
    )


@router.get("/chat/history/{session_id}", response_model=ChatHistoryResponse)
async def get_history(
    session_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    messages = await chat_service.get_chat_history(db, session_id)
    if not messages:
        raise HTTPException(status_code=404, detail="Session not found")

    base = _request_base(request)
    resolved = [
        {
            **m,
            "image_url": _absolutize(m.get("image_url"), base),
        }
        for m in messages
    ]

    brief_data = await chat_service.get_session_brief(db, session_id)
    brief = BriefSummary(**brief_data) if isinstance(brief_data, dict) else None

    return ChatHistoryResponse(
        session_id=session_id,
        messages=[ChatHistoryMessage(**m) for m in resolved],
        brief=brief,
    )


@router.delete("/chat/sessions/{session_id}")
async def delete_chat_session(
    session_id: str,
    db: AsyncSession = Depends(get_db),
):
    from app.models.chat import ChatSession

    session = await db.get(ChatSession, session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    await db.delete(session)
    return {"message": "Session deleted"}
