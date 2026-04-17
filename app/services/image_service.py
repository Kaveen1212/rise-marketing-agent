"""
app/services/image_service.py
─────────────────────────────────────────────────────────────────────────────
Image service — file storage + Stability AI (with placeholder fallback).

Files are written under `backend/storage/` and served via FastAPI's
StaticFiles mount at `/storage/...`. The public URL is built from the
request's scheme+host so it works from localhost and from deployed hosts.
─────────────────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import base64
import io
import textwrap
import uuid
from pathlib import Path
from typing import Optional

import httpx
import structlog
from fastapi import UploadFile
from PIL import Image, ImageDraw, ImageFont
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.image import ImageSource, PosterImage

log = structlog.get_logger()

STORAGE_ROOT = Path("storage")
UPLOAD_DIR = STORAGE_ROOT / "uploads"
GENERATED_DIR = STORAGE_ROOT / "generated"
APPROVED_DIR = STORAGE_ROOT / "approved"

for _d in (UPLOAD_DIR, GENERATED_DIR, APPROVED_DIR):
    _d.mkdir(parents=True, exist_ok=True)

ALLOWED_MIMES = {"image/jpeg", "image/png", "image/webp", "image/gif"}
MAX_UPLOAD_BYTES = 10 * 1024 * 1024  # 10 MB


def _storage_path(relative: str) -> str:
    """Relative path stored in DB. Served at {scheme}://{host}/storage/... at read time."""
    return f"/storage/{relative.lstrip('/')}"


def _public_url(relative: str, request_base: Optional[str] = None) -> str:
    """Backwards-compatible helper — returns a relative path.

    The URL is resolved to a full https://… URL at serve time using proxy
    headers, so the DB never bakes in a scheme (fixes mixed-content on
    HTTPS deployments fronted by an HTTP backend)."""
    return _storage_path(relative)


def _ext_for_mime(mime: str) -> str:
    return {
        "image/jpeg": ".jpg",
        "image/png": ".png",
        "image/webp": ".webp",
        "image/gif": ".gif",
    }.get(mime, ".bin")


async def save_upload(
    db: AsyncSession,
    file: UploadFile,
    caption: Optional[str],
    request_base: Optional[str],
) -> PosterImage:
    content_type = (file.content_type or "").lower()
    if content_type not in ALLOWED_MIMES:
        raise ValueError(f"Unsupported content type: {content_type or 'unknown'}")

    data = await file.read()
    if len(data) == 0:
        raise ValueError("Empty file")
    if len(data) > MAX_UPLOAD_BYTES:
        raise ValueError("File exceeds 10 MB limit")

    ext = Path(file.filename or "").suffix.lower() or _ext_for_mime(content_type)
    new_name = f"{uuid.uuid4().hex}{ext}"
    target = UPLOAD_DIR / new_name
    target.write_bytes(data)

    image = PosterImage(
        filename=file.filename or new_name,
        storage_path=str(target.as_posix()),
        url=_public_url(f"uploads/{new_name}", request_base),
        size_bytes=len(data),
        source=ImageSource.UPLOAD,
        caption=caption,
    )
    db.add(image)
    await db.flush()
    log.info("image_uploaded", image_id=str(image.id), size=len(data))
    return image


def _placeholder_png_bytes(prompt: str, reason: str = "") -> bytes:
    """1024x1024 visible placeholder when Stability AI is unavailable.

    Draws a RISE-branded card with the prompt wrapped on it. The point is
    that the frontend renders *something* instead of a broken image icon,
    while making it obvious that real generation didn't run.
    """
    W = H = 1024
    img = Image.new("RGB", (W, H), color=(15, 23, 42))  # rise-navy
    draw = ImageDraw.Draw(img)

    # Simple gradient-ish backdrop
    for y in range(H):
        shade = int(15 + (y / H) * 20)
        draw.line([(0, y), (W, y)], fill=(shade, shade + 8, shade + 35))

    # Accent bar
    draw.rectangle([(0, 0), (W, 16)], fill=(220, 38, 38))  # rise-red
    draw.rectangle([(0, H - 16), (W, H)], fill=(220, 38, 38))

    # Fonts — fall back to default if system fonts aren't available
    try:
        title_font = ImageFont.truetype("arial.ttf", 56)
        body_font = ImageFont.truetype("arial.ttf", 28)
        small_font = ImageFont.truetype("arial.ttf", 22)
    except OSError:
        title_font = ImageFont.load_default()
        body_font = ImageFont.load_default()
        small_font = ImageFont.load_default()

    draw.text((60, 80), "RISE Tech Village", fill=(220, 38, 38), font=title_font)
    draw.text((60, 160), "Poster Preview (placeholder)", fill=(226, 232, 240), font=body_font)

    wrapped = textwrap.fill(prompt[:400], width=40)
    draw.multiline_text((60, 260), wrapped, fill=(203, 213, 225), font=body_font, spacing=10)

    note_top = H - 200
    draw.text(
        (60, note_top),
        "Image generation is not configured.",
        fill=(248, 113, 113),
        font=small_font,
    )
    draw.text(
        (60, note_top + 40),
        "Set STABILITY_AI_API_KEY in backend/.env to generate real posters.",
        fill=(148, 163, 184),
        font=small_font,
    )
    if reason:
        draw.text(
            (60, note_top + 80),
            f"Reason: {reason[:80]}",
            fill=(148, 163, 184),
            font=small_font,
        )

    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


async def _call_stability_ai(prompt: str) -> bytes:
    api_key = settings.STABILITY_AI_API_KEY
    if api_key is None:
        raise RuntimeError("STABILITY_AI_API_KEY not configured")

    url = f"https://api.stability.ai/v1/generation/{settings.STABILITY_AI_MODEL}/text-to-image"
    headers = {
        "Authorization": f"Bearer {api_key.get_secret_value()}",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
    payload = {
        "text_prompts": [{"text": prompt, "weight": 1.0}],
        "cfg_scale": 7,
        "samples": 1,
        "steps": 30,
        "width": 1024,
        "height": 1024,
    }

    async with httpx.AsyncClient(timeout=120) as client:
        resp = await client.post(url, json=payload, headers=headers)
        resp.raise_for_status()
        data = resp.json()

    artifacts = data.get("artifacts") or []
    if not artifacts:
        raise RuntimeError("Stability AI returned no image")
    return base64.b64decode(artifacts[0]["base64"])


async def generate_image(
    db: AsyncSession,
    prompt: str,
    platform: str,
    session_id: Optional[str],
    request_base: Optional[str],
) -> PosterImage:
    try:
        image_bytes = await _call_stability_ai(prompt)
    except Exception as exc:
        log.warning("stability_ai_fallback", error=str(exc))
        image_bytes = _placeholder_png_bytes(prompt, reason=str(exc))

    new_name = f"{uuid.uuid4().hex}.png"
    target = GENERATED_DIR / new_name
    target.write_bytes(image_bytes)

    image = PosterImage(
        filename=new_name,
        storage_path=str(target.as_posix()),
        url=_public_url(f"generated/{new_name}", request_base),
        size_bytes=len(image_bytes),
        source=ImageSource.GENERATED,
        platform=platform,
        prompt=prompt,
        session_id=session_id,
    )
    db.add(image)
    await db.flush()
    log.info("image_generated", image_id=str(image.id), platform=platform)
    return image


async def approve_image(
    db: AsyncSession,
    image: PosterImage,
    caption: Optional[str],
    platforms: Optional[list[str]],
    scheduled_time,
    request_base: Optional[str],
) -> PosterImage:
    src_path = Path(image.storage_path)
    new_name = f"{uuid.uuid4().hex}{src_path.suffix or '.png'}"
    dest = APPROVED_DIR / new_name

    if src_path.exists():
        dest.write_bytes(src_path.read_bytes())
    else:
        dest.write_bytes(b"")

    image.source = ImageSource.APPROVED
    image.storage_path = str(dest.as_posix())
    image.url = _public_url(f"approved/{new_name}", request_base)
    if caption is not None:
        image.caption = caption
    if platforms is not None:
        image.platforms = platforms
    if scheduled_time is not None:
        image.scheduled_time = scheduled_time

    await db.flush()
    log.info("image_approved", image_id=str(image.id))
    return image


async def reject_image(db: AsyncSession, image: PosterImage) -> PosterImage:
    image.source = ImageSource.REJECTED
    await db.flush()
    log.info("image_rejected", image_id=str(image.id))
    return image


async def delete_image(db: AsyncSession, image: PosterImage) -> None:
    path = Path(image.storage_path)
    if path.exists():
        try:
            path.unlink()
        except OSError:
            pass
    await db.delete(image)
    await db.flush()
    log.info("image_deleted", image_id=str(image.id))
