"""
app/services/chat_service.py
─────────────────────────────────────────────────────────────────────────────
Chat service — drives the conversational brief UI.

Philosophy: the assistant is decisive. Each user turn it either generates a
poster immediately (the common case) or asks at most ONE short clarifying
question. No long interrogations. Claude converts the user's idea into a
detailed image prompt; the backend pipes that prompt into the image
generator and returns the finished poster in the same response.
─────────────────────────────────────────────────────────────────────────────
"""

import json
import re
import uuid
from typing import Optional

import structlog
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.chat import ChatMessage, ChatSession

log = structlog.get_logger()


SYSTEM_PROMPT = """You are the RISE Tech Village marketing image generator.

You help create social media posters for RISE Tech Village, Sri Lanka — a tech education hub running workshops, bootcamps, and meetups.

You are NOT a text-only chatbot. You have a real image generator wired up.
Every user turn, you will decide ONE of two things:

  1) GENERATE — you have enough to make a poster. This is the default.
  2) ASK — the user gave a greeting or something truly ambiguous. Ask ONE short question.

Be DECISIVE. Fill in reasonable defaults rather than asking. Do not ask
multiple questions. Do not ask about tone, audience, or platforms unless
the user explicitly mentions them — just pick sensible defaults (tone:
professional & inspiring, audience: students and young professionals in
Sri Lanka, platforms: instagram).

Always respond with ONE line of raw JSON. No markdown fences, no prose.

When generating, use this shape:
{"action":"generate","message":"<one short sentence, e.g. 'Generating a poster for your AI workshop now.'>","image_prompt":"<rich visual description: subject, composition, lighting, colors, mood, 1024x1024, add 'RISE Tech Village Sri Lanka branding, red and gold accent lighting, cinematic, ultra-detailed'>","caption":"<ready-to-post caption with 1-2 emojis and relevant hashtags>","platforms":["instagram"],"topic":"<one short phrase>","audience":"<who it's for>","tone":"<tone>","key_message":"<one sentence>"}

When asking, use this shape:
{"action":"ask","message":"<one short question>"}

Never refuse to generate. Never say you're text-only. Never list options or
present multiple prompt variants. Pick ONE and generate."""


def _build_llm() -> ChatAnthropic:
    return ChatAnthropic(
        model=settings.ANTHROPIC_MODEL,
        api_key=settings.ANTHROPIC_API_KEY.get_secret_value(),
        max_tokens=900,
        temperature=0.5,
    )


async def _get_or_create_session(db: AsyncSession, session_id: Optional[str]) -> ChatSession:
    if session_id:
        existing = await db.get(ChatSession, session_id)
        if existing is not None:
            return existing

    new_id = session_id or str(uuid.uuid4())
    session = ChatSession(id=new_id, status="chat")
    db.add(session)
    await db.flush()
    return session


async def _load_history(db: AsyncSession, session_id: str, limit: int = 40) -> list[ChatMessage]:
    result = await db.execute(
        select(ChatMessage)
        .where(ChatMessage.session_id == session_id)
        .order_by(ChatMessage.created_at.asc())
        .limit(limit)
    )
    return list(result.scalars().all())


def _to_lc_messages(history: list[ChatMessage]) -> list:
    msgs: list = [SystemMessage(content=SYSTEM_PROMPT)]
    for m in history:
        if m.role == "user":
            msgs.append(HumanMessage(content=m.content))
        else:
            msgs.append(AIMessage(content=m.content))
    return msgs


def _extract_json(raw: str) -> Optional[dict]:
    """Pull the first JSON object out of the reply — tolerate stray text."""
    text = raw.strip()
    # Strip markdown fences if present
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)

    # Try whole-string parse first
    try:
        data = json.loads(text)
        if isinstance(data, dict):
            return data
    except json.JSONDecodeError:
        pass

    # Fallback: grab the first {...} block
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        try:
            data = json.loads(match.group(0))
            if isinstance(data, dict):
                return data
        except json.JSONDecodeError:
            pass
    return None


def _is_generation_trigger(user_message: str) -> bool:
    """Quick heuristic: does the user clearly want an image now?"""
    t = user_message.lower()
    triggers = ("generate", "create an", "make an", "make a", "design", "draw",
                "image now", "poster now", "regenerate", "try again", "another one")
    return any(k in t for k in triggers)


async def process_chat_turn(
    db: AsyncSession,
    user_message: str,
    session_id: Optional[str],
    request_base: Optional[str],
) -> dict:
    """
    Run one chat turn. If Claude decides to generate (or the user clearly asks
    for it), immediately produce an image and return it in the same response.
    """
    # Lazy import to avoid circular module dependency
    from app.services import image_service

    session = await _get_or_create_session(db, session_id)

    db.add(ChatMessage(
        session_id=session.id,
        role="user",
        content=user_message,
    ))
    await db.flush()

    history = await _load_history(db, session.id)

    llm = _build_llm()
    response = await llm.ainvoke(_to_lc_messages(history))
    raw_reply = response.content if isinstance(response.content, str) else str(response.content)

    parsed = _extract_json(raw_reply) or {}
    action = parsed.get("action")
    message = (parsed.get("message") or raw_reply or "").strip()

    # If the user clearly asked to generate but the LLM tried to ask a question, override.
    if action != "generate" and _is_generation_trigger(user_message):
        action = "generate"
        # Synthesize a prompt from the full conversation if the model didn't give one
        if not parsed.get("image_prompt"):
            parsed["image_prompt"] = _fallback_prompt_from_history(history, user_message)
        if not message:
            message = "Generating a poster now."

    result: dict = {
        "session_id": session.id,
        "message": message or "Working on it…",
        "status": "chat",
        "image_url": None,
        "image_id": None,
        "brief": None,
        "platforms": None,
    }

    if action == "generate":
        image_prompt = (parsed.get("image_prompt") or "").strip() or _fallback_prompt_from_history(history, user_message)
        platforms = parsed.get("platforms") or ["instagram"]
        platform = platforms[0] if platforms else "instagram"

        try:
            image = await image_service.generate_image(
                db=db,
                prompt=image_prompt,
                platform=platform,
                session_id=session.id,
                request_base=request_base,
            )
            result["image_url"] = image.url
            result["image_id"] = str(image.id)
            # "ready" — the image is rendered; the review card (Approve/Reject)
            # shows for every status except "done", which means already approved.
            result["status"] = "ready"
        except Exception as exc:
            log.error("image_generation_failed", error=str(exc))
            result["status"] = "chat"
            result["message"] = f"I hit a snag generating the image ({exc}). Try again?"

        brief = {
            "topic":       parsed.get("topic"),
            "audience":    parsed.get("audience"),
            "tone":        parsed.get("tone"),
            "key_message": parsed.get("key_message"),
            "caption":     parsed.get("caption"),
            "platforms":   platforms,
        }
        result["brief"] = {k: v for k, v in brief.items() if v is not None} or None
        result["platforms"] = platforms
        session.brief = result["brief"]

    elif action == "ask":
        result["status"] = "needs_clarification"

    session.status = result["status"]
    db.add(ChatMessage(
        session_id=session.id,
        role="assistant",
        content=result["message"],
        image_url=result["image_url"],
    ))
    await db.flush()

    log.info("chat_turn", session_id=session.id, action=action, status=result["status"])
    return result


def _fallback_prompt_from_history(history: list[ChatMessage], latest_user_message: str) -> str:
    """Build a safe image prompt if the LLM didn't provide one."""
    user_texts = [m.content for m in history if m.role == "user"]
    user_texts.append(latest_user_message)
    subject = " — ".join(user_texts[-3:]).strip()
    return (
        f"Marketing poster for RISE Tech Village, Sri Lanka. "
        f"{subject}. "
        f"Cinematic composition, vibrant red and gold accent lighting, ultra-detailed, "
        f"professional, 1024x1024, suitable for Instagram."
    )


async def get_chat_history(db: AsyncSession, session_id: str) -> list[dict]:
    messages = await _load_history(db, session_id, limit=500)
    return [
        {
            "role": m.role,
            "content": m.content,
            "image_url": m.image_url,
            "image_id": str(m.image_id) if m.image_id else None,
        }
        for m in messages
    ]


async def list_sessions(db: AsyncSession, limit: int = 100) -> list[dict]:
    """Return a summary of every chat session, newest first."""
    from sqlalchemy import desc, func

    result = await db.execute(
        select(
            ChatSession.id,
            ChatSession.status,
            ChatSession.created_at,
            ChatSession.updated_at,
            func.count(ChatMessage.id).label("message_count"),
        )
        .outerjoin(ChatMessage, ChatMessage.session_id == ChatSession.id)
        .group_by(ChatSession.id)
        .order_by(desc(ChatSession.updated_at))
        .limit(limit)
    )

    sessions: list[dict] = []
    for row in result.all():
        sid, status, created_at, updated_at, message_count = row

        first_user_msg = await db.execute(
            select(ChatMessage.content)
            .where(ChatMessage.session_id == sid, ChatMessage.role == "user")
            .order_by(ChatMessage.created_at.asc())
            .limit(1)
        )
        first_text = first_user_msg.scalar_one_or_none() or "New chat"
        title = first_text.strip().split("\n")[0][:80]

        sessions.append({
            "session_id": sid,
            "title": title or "New chat",
            "status": status or "chat",
            "created_at": created_at.isoformat(),
            "updated_at": updated_at.isoformat(),
            "message_count": message_count or 0,
        })
    return sessions


async def get_session_brief(db: AsyncSession, session_id: str) -> Optional[dict]:
    session = await db.get(ChatSession, session_id)
    return session.brief if session is not None else None


# Backwards-compatible name used by the router
async def process_chat_message(
    db: AsyncSession,
    user_message: str,
    session_id: Optional[str],
    request_base: Optional[str] = None,
) -> dict:
    return await process_chat_turn(
        db=db,
        user_message=user_message,
        session_id=session_id,
        request_base=request_base,
    )
