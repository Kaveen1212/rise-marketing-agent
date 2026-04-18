"""
app/api/images.py
─────────────────────────────────────────────────────────────────────────────
Image management API — upload, approve, reject, and list images.

Routes:
  POST   /poster/images/upload           → upload your own image
  GET    /poster/images/uploads          → list uploaded images
  DELETE /poster/images/uploads/{id}     → delete an uploaded image
  GET    /poster/images/approved         → list approved images
  GET    /poster/images/pending          → list generated (pending review) images
  POST   /poster/images/{id}/approve     → approve image → save to approved folder
  POST   /poster/images/{id}/reject      → reject image → remove from storage
─────────────────────────────────────────────────────────────────────────────
"""

import base64
import shutil
import uuid
from datetime import datetime
from io import BytesIO
from pathlib import Path
from typing import Optional

import structlog
from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

log = structlog.get_logger()
router = APIRouter()

STORAGE_DIR = Path("storage/posters")
UPLOADS_DIR = STORAGE_DIR / "uploads"
APPROVED_DIR = STORAGE_DIR / "approved"
GENERATED_DIR = STORAGE_DIR / "generated"
REJECTED_DIR = STORAGE_DIR / "rejected"

# Ensure directories exist
for d in [UPLOADS_DIR, APPROVED_DIR, GENERATED_DIR, REJECTED_DIR]:
    d.mkdir(parents=True, exist_ok=True)

ALLOWED_MIME_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB


# ─────────────────────────────────────────────────────────────────────────────
# Response schemas
# ─────────────────────────────────────────────────────────────────────────────

class ImageInfo(BaseModel):
    image_id: str
    url: str
    filename: str
    created_at: str
    size_bytes: int
    source: str  # "upload" | "generated" | "approved"
    platform: Optional[str] = None
    caption: Optional[str] = None
    scheduled_time: Optional[str] = None


class ApproveImageRequest(BaseModel):
    caption: Optional[str] = None
    platforms: Optional[list[str]] = None
    scheduled_time: Optional[str] = None  # ISO string or human-readable


class ApproveImageResponse(BaseModel):
    image_id: str
    approved_url: str
    message: str
    scheduled_time: Optional[str] = None


class RejectImageResponse(BaseModel):
    image_id: str
    message: str


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _detect_mime_type(data: bytes) -> str:
    """Detect MIME type from magic bytes."""
    if data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif"
    return "application/octet-stream"


def _file_to_data_uri(path: Path) -> str:
    """Read an image file and return as a base64 data URI."""
    data = path.read_bytes()
    _mime_map = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp", ".gif": "image/gif"}
    mime = _mime_map.get(path.suffix.lower(), "image/jpeg")
    return f"data:{mime};base64,{base64.b64encode(data).decode()}"


def _find_image(image_id: str) -> Optional[tuple[Path, str]]:
    """
    Find an image by ID in uploads, generated, or approved directories.
    Returns (file_path, source) or None.
    """
    for source, directory in [
        ("upload", UPLOADS_DIR),
        ("generated", GENERATED_DIR),
        ("approved", APPROVED_DIR),
    ]:
        # Direct file
        for ext in (".jpg", ".jpeg", ".png", ".webp"):
            path = directory / f"{image_id}{ext}"
            if path.exists():
                return path, source
        # Subdirectory (approved images stored per brief_id)
        for subdir in directory.iterdir():
            if subdir.is_dir():
                for ext in (".jpg", ".jpeg", ".png", ".webp"):
                    path = subdir / f"{image_id}{ext}"
                    if path.exists():
                        return path, source

    return None


def _list_images_in_dir(directory: Path, source: str) -> list[ImageInfo]:
    """List all images in a directory as ImageInfo objects."""
    images = []
    if not directory.exists():
        return images

    for f in sorted(directory.rglob("*.jpg"), key=lambda p: p.stat().st_mtime, reverse=True):
        image_id = f.stem
        stat = f.stat()
        url = _file_to_data_uri(f)
        images.append(ImageInfo(
            image_id=image_id,
            url=url,
            filename=f.name,
            created_at=datetime.fromtimestamp(stat.st_mtime).isoformat(),
            size_bytes=stat.st_size,
            source=source,
        ))

    return images


# ─────────────────────────────────────────────────────────────────────────────
# POST /poster/images/upload — upload your own image
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/images/upload", response_model=ImageInfo)
async def upload_image(
    file: UploadFile = File(...),
    caption: Optional[str] = Form(None),
):
    """
    Upload your own image to use in social media posts.

    Accepts JPEG, PNG, WebP. Max 10MB.
    Returns the image URL for use in posts.
    """
    # Read file
    data = await file.read()

    if len(data) > MAX_FILE_SIZE:
        raise HTTPException(status_code=413, detail="File too large. Maximum size is 10MB.")

    # Validate MIME type
    mime = _detect_mime_type(data)
    if mime not in ALLOWED_MIME_TYPES:
        raise HTTPException(
            status_code=415,
            detail=f"Unsupported file type. Allowed: JPEG, PNG, WebP, GIF."
        )

    # Save as JPEG for consistency
    try:
        from PIL import Image
        img = Image.open(BytesIO(data))
        if img.mode in ("RGBA", "P"):
            img = img.convert("RGB")

        image_id = uuid.uuid4().hex[:12]
        UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
        file_path = UPLOADS_DIR / f"{image_id}.jpg"

        out = BytesIO()
        img.save(out, "JPEG", quality=92)
        file_path.write_bytes(out.getvalue())

    except Exception as e:
        log.error("image_upload_failed", error=str(e))
        raise HTTPException(status_code=422, detail="Failed to process image file.")

    stat = file_path.stat()
    log.info("image_uploaded", image_id=image_id, size=stat.st_size)

    return ImageInfo(
        image_id=image_id,
        url=_file_to_data_uri(file_path),
        filename=f"{image_id}.jpg",
        created_at=datetime.now().isoformat(),
        size_bytes=stat.st_size,
        source="upload",
        caption=caption,
    )


# ─────────────────────────────────────────────────────────────────────────────
# GET /poster/images/uploads — list uploaded images
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/images/uploads", response_model=list[ImageInfo])
async def list_uploads():
    """List all images you have uploaded."""
    return _list_images_in_dir(UPLOADS_DIR, "upload")


# ─────────────────────────────────────────────────────────────────────────────
# DELETE /poster/images/uploads/{image_id} — delete an upload
# ─────────────────────────────────────────────────────────────────────────────

@router.delete("/images/uploads/{image_id}")
async def delete_upload(image_id: str):
    """Delete an uploaded image."""
    result = _find_image(image_id)
    if not result:
        raise HTTPException(status_code=404, detail="Image not found.")

    file_path, source = result
    if source != "upload":
        raise HTTPException(status_code=400, detail="Only uploaded images can be deleted this way.")

    file_path.unlink()
    log.info("upload_deleted", image_id=image_id)
    return {"message": "Image deleted.", "image_id": image_id}


# ─────────────────────────────────────────────────────────────────────────────
# GET /poster/images/approved — list approved images
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/images/approved", response_model=list[ImageInfo])
async def list_approved():
    """List all approved images saved to the approved folder."""
    images = []
    if not APPROVED_DIR.exists():
        return images

    # Walk subdirectories (organized by brief_id or flat)
    for f in sorted(APPROVED_DIR.rglob("*.jpg"), key=lambda p: p.stat().st_mtime, reverse=True):
        stat = f.stat()
        url = _file_to_data_uri(f)

        # Try to read caption from sidecar file
        caption_file = f.with_suffix(".txt")
        caption = caption_file.read_text(encoding="utf-8") if caption_file.exists() else None

        # Try to read schedule from sidecar
        schedule_file = f.parent / "schedule.txt"
        scheduled_time = schedule_file.read_text(encoding="utf-8") if schedule_file.exists() else None

        # Determine platform from filename or parent folder name
        platform = None
        parent_name = f.parent.name
        if parent_name in ("instagram", "facebook", "linkedin", "tiktok"):
            platform = parent_name

        images.append(ImageInfo(
            image_id=f.stem,
            url=url,
            filename=f.name,
            created_at=datetime.fromtimestamp(stat.st_mtime).isoformat(),
            size_bytes=stat.st_size,
            source="approved",
            platform=platform,
            caption=caption,
            scheduled_time=scheduled_time,
        ))

    return images


# ─────────────────────────────────────────────────────────────────────────────
# GET /poster/images/pending — list pending (generated, not yet reviewed) images
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/images/pending", response_model=list[ImageInfo])
async def list_pending():
    """List all AI-generated images waiting for approval."""
    return _list_images_in_dir(GENERATED_DIR, "generated")


# ─────────────────────────────────────────────────────────────────────────────
# POST /poster/images/{image_id}/approve — approve an image
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/images/{image_id}/approve", response_model=ApproveImageResponse)
async def approve_image(image_id: str, body: ApproveImageRequest = ApproveImageRequest()):
    """
    Approve an image — saves it to the approved folder.

    The image is organized under storage/posters/approved/
    Optional caption and scheduled time are saved as sidecar files.
    """
    result = _find_image(image_id)
    if not result:
        raise HTTPException(status_code=404, detail="Image not found.")

    file_path, source = result

    if source == "approved":
        # Already approved
        return ApproveImageResponse(
            image_id=image_id,
            approved_url=_file_to_data_uri(file_path),
            message="Image was already approved.",
        )

    # Create approved directory for this image
    approved_subdir = APPROVED_DIR / image_id
    approved_subdir.mkdir(parents=True, exist_ok=True)

    # Copy image to approved folder
    approved_path = approved_subdir / f"{image_id}.jpg"
    shutil.copy2(file_path, approved_path)

    # Save caption sidecar
    if body.caption:
        (approved_subdir / f"{image_id}.txt").write_text(body.caption, encoding="utf-8")

    # Determine scheduled time
    scheduled_time = body.scheduled_time
    if not scheduled_time and body.platforms:
        from app.agents.scheduling_agent import get_suggested_post_time
        scheduled_time = get_suggested_post_time(
            platform=body.platforms[0] if body.platforms else "instagram"
        )

    if scheduled_time:
        (approved_subdir / "schedule.txt").write_text(scheduled_time, encoding="utf-8")

    # Save platforms info
    if body.platforms:
        (approved_subdir / "platforms.txt").write_text(
            ",".join(body.platforms), encoding="utf-8"
        )

    # Delete original from generated (if it was generated)
    if source == "generated":
        try:
            file_path.unlink()
        except Exception:
            pass

    approved_url = _file_to_data_uri(approved_path)

    log.info("image_approved", image_id=image_id, scheduled_time=scheduled_time)

    return ApproveImageResponse(
        image_id=image_id,
        approved_url=approved_url,
        message="Image approved and saved to your folder!",
        scheduled_time=scheduled_time,
    )


# ─────────────────────────────────────────────────────────────────────────────
# POST /poster/images/{image_id}/reject — reject an image
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/images/{image_id}/reject", response_model=RejectImageResponse)
async def reject_image(image_id: str):
    """
    Reject an image — removes it from storage.
    Uploaded images are not deleted; only AI-generated ones.
    """
    result = _find_image(image_id)
    if not result:
        raise HTTPException(status_code=404, detail="Image not found.")

    file_path, source = result

    if source == "upload":
        # Don't delete uploads — just acknowledge
        return RejectImageResponse(
            image_id=image_id,
            message="Generated image rejected. Your uploaded image remains in your library.",
        )

    if source == "approved":
        # Move back to rejected
        rejected_subdir = REJECTED_DIR / image_id
        rejected_subdir.mkdir(parents=True, exist_ok=True)

        # Move the whole approved subfolder
        parent_dir = file_path.parent
        if parent_dir != APPROVED_DIR:
            shutil.move(str(parent_dir), str(rejected_subdir))
        else:
            shutil.move(str(file_path), str(rejected_subdir / f"{image_id}.jpg"))

        log.info("approved_image_rejected", image_id=image_id)
        return RejectImageResponse(
            image_id=image_id,
            message="Image removed from approved folder.",
        )

    # Generated image — delete it
    try:
        file_path.unlink()
        log.info("generated_image_rejected", image_id=image_id)
    except Exception as e:
        log.warning("delete_failed", image_id=image_id, error=str(e))

    return RejectImageResponse(
        image_id=image_id,
        message="Image rejected and removed.",
    )
