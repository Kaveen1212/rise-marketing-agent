"""
app/api/chat.py
─────────────────────────────────────────────────────────────────────────────
Conversational chat API — the main entry point for the marketing agent.

Users type natural language prompts here. Claude parses intent, generates
marketing content (images + copy), and returns structured responses.

Routes:
  POST /poster/chat/message   → send a message, get AI response
  GET  /poster/chat/history/{session_id} → get conversation history
  POST /poster/chat/generate  → directly generate an image from a prompt
─────────────────────────────────────────────────────────────────────────────
"""

import base64
import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

import structlog
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.config import settings

log = structlog.get_logger()
router = APIRouter()

STORAGE_DIR = Path(__file__).parent.parent.parent / "storage" / "posters"
SESSIONS_DIR = Path(__file__).parent.parent.parent / "storage" / "chat_sessions"
SESSIONS_DIR.mkdir(parents=True, exist_ok=True)


# ─────────────────────────────────────────────────────────────────────────────
# File-based session persistence
# ─────────────────────────────────────────────────────────────────────────────

def _session_path(session_id: str) -> Path:
    return SESSIONS_DIR / f"{session_id}.json"


def _save_session(session_id: str, messages: list[dict], brief: Optional[dict] = None, status: str = "chat") -> None:
    path = _session_path(session_id)
    existing: dict = {}
    if path.exists():
        try:
            existing = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            pass

    title = existing.get("title") or next(
        (m["content"][:60] for m in messages if m.get("role") == "user"), "New Chat"
    )

    path.write_text(json.dumps({
        "session_id": session_id,
        "title": title,
        "created_at": existing.get("created_at", datetime.now().isoformat()),
        "updated_at": datetime.now().isoformat(),
        "status": status,
        "brief": brief or existing.get("brief"),
        "messages": messages,
    }, ensure_ascii=False), encoding="utf-8")


def _load_session(session_id: str) -> Optional[dict]:
    path = _session_path(session_id)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _load_messages(session_id: str) -> list[dict]:
    data = _load_session(session_id)
    return data.get("messages", []) if data else []


def _image_id_to_data_uri(image_id: str) -> Optional[str]:
    """Find a saved image by ID and return as base64 data URI."""
    search_dirs = [
        STORAGE_DIR / "generated",
        STORAGE_DIR / "approved" / image_id,
        STORAGE_DIR / "uploads",
    ]
    for directory in search_dirs:
        if not directory.exists():
            continue
        for ext in (".jpg", ".jpeg", ".png"):
            p = directory / f"{image_id}{ext}"
            if p.exists():
                return f"data:image/jpeg;base64,{base64.b64encode(p.read_bytes()).decode()}"
    return None


# ─────────────────────────────────────────────────────────────────────────────
# Request / Response schemas
# ─────────────────────────────────────────────────────────────────────────────

class ChatMessageRequest(BaseModel):
    message: str
    session_id: Optional[str] = None


class GenerateImageRequest(BaseModel):
    prompt: str
    platform: str = "instagram"  # instagram | facebook | linkedin
    style: str = "professional"  # professional | vibrant | minimal


class ChatResponse(BaseModel):
    session_id: str
    message: str
    status: str  # "ready" | "needs_clarification" | "generating" | "done"
    image_url: Optional[str] = None
    image_id: Optional[str] = None
    brief: Optional[dict] = None
    suggested_post_time: Optional[str] = None
    platforms: Optional[list[str]] = None


# ─────────────────────────────────────────────────────────────────────────────
# Helper — call Claude to parse intent and generate response
# ─────────────────────────────────────────────────────────────────────────────

def _build_system_prompt() -> str:
    return """You are RISE Marketing Agent — an AI assistant for RISE Tech Village Sri Lanka's social media marketing team.

Your job is to generate marketing images and social media content for ANY topic the user requests.
You MUST always attempt to generate an image — never refuse or redirect.

When a user sends you a message or an image generation prompt:
1. If the user provides a detailed image prompt (e.g. describing a vehicle, product, scene, concept), use it directly as image_prompt — do NOT refuse it.
2. Wrap the user's prompt with RISE Tech Village brand style: dark navy (#1A1A2E) environment, red accent (#E94560) lighting, professional marketing aesthetic.
3. Always respond with JSON in one of these formats:

   When ready to generate (always prefer this):
   {"status": "ready", "topic": "...", "audience": "...", "tone": "professional", "platforms": ["instagram","facebook"], "key_message": "...", "image_prompt": "...", "caption": "..."}

   Only if truly missing critical info:
   {"status": "needs_clarification", "question": "..."}

   For greetings or pure conversation only:
   {"status": "chat", "message": "..."}

Rules:
- If the user pastes an image prompt or describes a visual scene → status must be "ready", use their description as image_prompt.
- The image_prompt field should be detailed, cinematic, and photorealistic.
- RISE brand colors: dark navy (#1A1A2E), red accent (#E94560), clean modern tech aesthetic.
- Never say you cannot generate images. Always set status to "ready" when given any visual description.

Always respond with valid JSON only. No markdown, no extra text."""


async def _call_claude(messages: list[dict]) -> dict:
    """Call Claude API and parse the JSON response."""
    import anthropic
    import json

    client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY.get_secret_value())

    response = await client.messages.create(
        model=settings.ANTHROPIC_MODEL,
        max_tokens=1024,
        system=_build_system_prompt(),
        messages=messages,
    )

    text = response.content[0].text.strip()

    # Strip markdown code fences if present
    if text.startswith("```"):
        lines = text.split("\n")
        text = "\n".join(lines[1:-1]) if len(lines) > 2 else text

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # Fallback: treat as plain chat message
        return {"status": "chat", "message": text}


def _generate_placeholder_image(prompt: str, platform: str) -> tuple[str, str]:
    """
    Generate a placeholder/real image using the existing design tools.
    Returns (image_url, image_id).
    """
    from PIL import Image, ImageDraw, ImageFont
    import io

    dimensions = {
        "instagram": (1080, 1080),
        "facebook": (1200, 630),
        "linkedin": (1200, 627),
        "tiktok": (1080, 1920),
    }
    width, height = dimensions.get(platform, (1080, 1080))

    # Try Stability AI first
    try:
        from app.config import settings
        if settings.STABILITY_AI_API_KEY:
            import httpx

            api_key = settings.STABILITY_AI_API_KEY.get_secret_value()
            w = max(512, min(1024, (width // 64) * 64))
            h = max(512, min(1024, (height // 64) * 64))
            if w * h > 1048576:
                w, h = 1024, 1024

            response = httpx.post(
                f"https://api.stability.ai/v1/generation/{settings.STABILITY_AI_MODEL}/text-to-image",
                headers={"Authorization": f"Bearer {api_key}", "Accept": "application/json"},
                json={
                    "text_prompts": [{"text": prompt, "weight": 1.0}],
                    "cfg_scale": 7, "width": w, "height": h, "samples": 1, "steps": 30,
                },
                timeout=120.0,
            )
            response.raise_for_status()
            image_bytes = base64.b64decode(response.json()["artifacts"][0]["base64"])

            image_id = uuid.uuid4().hex[:12]
            save_dir = STORAGE_DIR / "generated"
            save_dir.mkdir(parents=True, exist_ok=True)
            file_path = save_dir / f"{image_id}.jpg"
            from app.tools.design_tools import _overlay_logo
            image_bytes = _overlay_logo(image_bytes)
            file_path.write_bytes(image_bytes)
            data_uri = f"data:image/jpeg;base64,{base64.b64encode(image_bytes).decode()}"
            return data_uri, image_id
    except Exception as e:
        log.warning("stability_ai_failed", error=str(e))

    # Fallback: branded placeholder
    img = Image.new("RGB", (width, height), (26, 26, 46))  # dark navy
    draw = ImageDraw.Draw(img)

    # Brand accent stripes
    draw.rectangle([(0, 0), (width, 10)], fill=(233, 69, 96))
    draw.rectangle([(0, height - 10), (width, height)], fill=(233, 69, 96))

    # Diagonal accent
    draw.polygon([(0, 0), (width // 3, 0), (0, height // 3)], fill=(40, 40, 80))

    try:
        font_large = ImageFont.truetype("arial.ttf", max(32, width // 20))
        font_med = ImageFont.truetype("arial.ttf", max(20, width // 32))
        font_small = ImageFont.truetype("arial.ttf", max(16, width // 40))
    except OSError:
        font_large = ImageFont.load_default()
        font_med = font_large
        font_small = font_large

    # Brand name
    draw.text((width // 2, height // 3), "RISE Tech Village", fill=(233, 69, 96),
              font=font_large, anchor="mm")

    # Platform badge
    draw.rounded_rectangle(
        [(width // 2 - 80, height // 3 + 50), (width // 2 + 80, height // 3 + 85)],
        radius=12, fill=(233, 69, 96)
    )
    draw.text((width // 2, height // 3 + 67), platform.upper(), fill=(255, 255, 255),
              font=font_small, anchor="mm")

    # Prompt summary
    short = prompt[:60] + "..." if len(prompt) > 60 else prompt
    draw.text((width // 2, height // 2 + 20), short, fill=(180, 180, 200),
              font=font_med, anchor="mm")

    # Watermark
    draw.text((width // 2, height - 40), "AI-Generated • RISE Marketing",
              fill=(80, 80, 100), font=font_small, anchor="mm")

    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=90)
    image_bytes = buf.getvalue()

    image_id = uuid.uuid4().hex[:12]
    save_dir = STORAGE_DIR / "generated"
    save_dir.mkdir(parents=True, exist_ok=True)
    file_path = save_dir / f"{image_id}.jpg"
    file_path.write_bytes(image_bytes)

    data_uri = f"data:image/jpeg;base64,{base64.b64encode(image_bytes).decode()}"
    return data_uri, image_id


# ─────────────────────────────────────────────────────────────────────────────
# POST /poster/chat/message
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/chat/message", response_model=ChatResponse)
async def send_message(body: ChatMessageRequest):
    """
    Send a message to the marketing agent.

    The agent understands natural language and can:
    - Parse campaign briefs from casual descriptions
    - Generate marketing images with AI
    - Suggest optimal posting times
    - Answer questions about the platform

    Returns a structured response including any generated images.
    """
    session_id = body.session_id or uuid.uuid4().hex

    # Load persisted history and append the new user message
    messages = _load_messages(session_id)
    messages.append({"role": "user", "content": body.message, "timestamp": datetime.now().isoformat()})

    # Keep last 20 messages for Claude context (strip timestamps/image_id for API call)
    recent_messages = [{"role": m["role"], "content": m["content"]} for m in messages[-20:]]

    log.info("chat_message_received", session_id=session_id, message_len=len(body.message))

    # Call Claude
    try:
        ai_response = await _call_claude(recent_messages)
    except Exception as e:
        log.error("claude_call_failed", error=str(e))
        raise HTTPException(status_code=503, detail="AI service unavailable. Please try again.")

    status = ai_response.get("status", "chat")

    # If ready to generate — create the image
    if status == "ready":
        image_prompt = ai_response.get("image_prompt", body.message)
        platforms = ai_response.get("platforms", ["instagram"])
        primary_platform = platforms[0] if platforms else "instagram"

        topic = ai_response.get("topic", "marketing content")
        # If user gave a detailed prompt, use it as-is; otherwise wrap with RISE context
        if len(image_prompt) > 80:
            full_prompt = (
                f"{image_prompt}. "
                f"RISE Tech Village Sri Lanka branding, dark navy (#1A1A2E) accent, red highlight (#E94560), "
                f"professional marketing quality, photorealistic."
            )
        else:
            full_prompt = (
                f"Professional social media marketing image for RISE Tech Village Sri Lanka tech community. "
                f"Topic: {topic}. {image_prompt}. "
                f"Dark navy background (#1A1A2E), red accent color (#E94560), modern tech aesthetic, "
                f"clean typography, professional quality."
            )

        image_url, image_id = _generate_placeholder_image(full_prompt, primary_platform)

        # Get scheduling recommendation
        from app.agents.scheduling_agent import get_suggested_post_time
        suggested_time = get_suggested_post_time(
            platform=primary_platform,
            topic=topic,
            audience=ai_response.get("audience", "general"),
        )

        caption = ai_response.get("caption", f"🚀 {topic} | RISE Tech Village")

        assistant_msg = (
            f"I've generated a marketing image for **{topic}**!\n\n"
            f"📱 Platforms: {', '.join(platforms)}\n"
            f"🎯 Audience: {ai_response.get('audience', 'General')}\n"
            f"💬 Caption: {caption}\n"
            f"⏰ Best time to post: {suggested_time}\n\n"
            f"Review the image below and click **Approve** to save it to your folder, or **Reject** to try again."
        )

        brief = {
            "topic": ai_response.get("topic"),
            "audience": ai_response.get("audience"),
            "tone": ai_response.get("tone"),
            "key_message": ai_response.get("key_message"),
            "caption": caption,
            "platforms": platforms,
        }

        messages.append({
            "role": "assistant",
            "content": assistant_msg,
            "image_id": image_id,
            "timestamp": datetime.now().isoformat(),
        })
        _save_session(session_id, messages, brief=brief, status="ready")

        return ChatResponse(
            session_id=session_id,
            message=assistant_msg,
            status="ready",
            image_url=image_url,
            image_id=image_id,
            brief=brief,
            suggested_post_time=suggested_time,
            platforms=platforms,
        )

    elif status == "needs_clarification":
        question = ai_response.get("question", "Could you provide more details?")
        messages.append({"role": "assistant", "content": question, "timestamp": datetime.now().isoformat()})
        _save_session(session_id, messages, status="needs_clarification")
        return ChatResponse(
            session_id=session_id,
            message=question,
            status="needs_clarification",
        )

    else:
        # General chat
        message = ai_response.get("message", "How can I help you create content today?")
        messages.append({"role": "assistant", "content": message, "timestamp": datetime.now().isoformat()})
        _save_session(session_id, messages, status="chat")
        return ChatResponse(
            session_id=session_id,
            message=message,
            status="chat",
        )


# ─────────────────────────────────────────────────────────────────────────────
# POST /poster/chat/generate — direct image generation from prompt
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/chat/generate", response_model=ChatResponse)
async def generate_image(body: GenerateImageRequest):
    """
    Directly generate a marketing image from a prompt.
    No conversation context needed — just a prompt and platform.
    """
    session_id = uuid.uuid4().hex

    full_prompt = (
        f"Professional social media marketing image for RISE Tech Village Sri Lanka. "
        f"{body.prompt}. Style: {body.style}. "
        f"Dark navy background, red accent (#E94560), modern tech aesthetic."
    )

    image_url, image_id = _generate_placeholder_image(full_prompt, body.platform)

    from app.agents.scheduling_agent import get_suggested_post_time
    suggested_time = get_suggested_post_time(platform=body.platform, topic=body.prompt)

    return ChatResponse(
        session_id=session_id,
        message=f"Image generated for {body.platform}! Review and approve or reject below.",
        status="ready",
        image_url=image_url,
        image_id=image_id,
        suggested_post_time=suggested_time,
        platforms=[body.platform],
    )


# ─────────────────────────────────────────────────────────────────────────────
# GET /poster/chat/sessions — list all sessions
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/chat/sessions")
async def list_sessions():
    """List all saved chat sessions, newest first."""
    sessions = []
    for f in sorted(SESSIONS_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            sessions.append({
                "session_id": data["session_id"],
                "title": data.get("title", "Untitled"),
                "status": data.get("status", "chat"),
                "created_at": data.get("created_at", ""),
                "updated_at": data.get("updated_at", ""),
                "message_count": len(data.get("messages", [])),
            })
        except Exception:
            pass
    return {"sessions": sessions}


# ─────────────────────────────────────────────────────────────────────────────
# DELETE /poster/chat/sessions/{session_id} — delete a session
# ─────────────────────────────────────────────────────────────────────────────

@router.delete("/chat/sessions/{session_id}")
async def delete_session(session_id: str):
    """Delete a saved chat session."""
    path = _session_path(session_id)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Session not found.")
    path.unlink()
    return {"message": "Session deleted.", "session_id": session_id}


# ─────────────────────────────────────────────────────────────────────────────
# GET /poster/chat/history/{session_id}
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/chat/history/{session_id}")
async def get_history(session_id: str):
    """Get the full conversation history for a session, with images as base64 data URIs."""
    data = _load_session(session_id)
    if not data:
        return {"session_id": session_id, "messages": [], "brief": None}

    enriched = []
    for m in data.get("messages", []):
        msg: dict = {"role": m["role"], "content": m["content"]}
        if m.get("timestamp"):
            msg["timestamp"] = m["timestamp"]
        image_id = m.get("image_id")
        if image_id:
            msg["image_id"] = image_id
            uri = _image_id_to_data_uri(image_id)
            if uri:
                msg["image_url"] = uri
        enriched.append(msg)

    return {"session_id": session_id, "messages": enriched, "brief": data.get("brief")}
