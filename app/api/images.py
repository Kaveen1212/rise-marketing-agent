"""
app/api/images.py
─────────────────────────────────────────────────────────────────────────────
Image gallery endpoints for the Next.js review UI.

Routes:
  POST   /poster/images/upload               → upload a file
  GET    /poster/images/uploads              → list uploaded images
  DELETE /poster/images/uploads/{id}         → delete an uploaded image
  GET    /poster/images/approved             → list approved images
  GET    /poster/images/pending              → list pending (generated) images
  POST   /poster/images/{id}/approve         → approve image + optional schedule
  POST   /poster/images/{id}/reject          → reject image
─────────────────────────────────────────────────────────────────────────────
"""

from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.models.image import ImageSource, PosterImage
from app.schemas.image import (
    ApproveImageRequest,
    ApproveImageResponse,
    DeleteImageResponse,
    ImageInfo,
    RejectImageResponse,
)
from app.services import image_service

log = structlog.get_logger()

router = APIRouter()


def _request_base(request: Request) -> str:
    # Honor reverse-proxy / tunnel headers so HTTPS Vercel clients get HTTPS
    # URLs back (no mixed-content warnings). Falls back to the raw request URL
    # when headers are absent (e.g. local development).
    proto = request.headers.get("x-forwarded-proto", request.url.scheme)
    host = request.headers.get("x-forwarded-host") or request.headers.get("host") or request.url.netloc
    return f"{proto}://{host}"


def _to_info(image: PosterImage, request_base: str) -> ImageInfo:
    # Ensure URL is absolute for the current host
    url = image.url
    if url.startswith("/"):
        url = f"{request_base}{url}"
    return ImageInfo(
        image_id=str(image.id),
        url=url,
        filename=image.filename,
        created_at=image.created_at,
        size_bytes=image.size_bytes,
        source=image.source.value,
        platform=image.platform,
        caption=image.caption,
        scheduled_time=image.scheduled_time,
    )


async def _list_by_source(
    db: AsyncSession, source: ImageSource, request_base: str
) -> list[ImageInfo]:
    result = await db.execute(
        select(PosterImage)
        .where(PosterImage.source == source)
        .order_by(PosterImage.created_at.desc())
    )
    return [_to_info(img, request_base) for img in result.scalars().all()]


# ─────────────────────────────────────────────────────────────────────────────
# Upload
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/images/upload", response_model=ImageInfo)
async def upload_image(
    request: Request,
    file: UploadFile = File(...),
    caption: str | None = Form(default=None),
    db: AsyncSession = Depends(get_db),
):
    try:
        image = await image_service.save_upload(
            db=db,
            file=file,
            caption=caption,
            request_base=_request_base(request),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return _to_info(image, _request_base(request))


# ─────────────────────────────────────────────────────────────────────────────
# List galleries
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/images/uploads", response_model=list[ImageInfo])
async def list_uploaded(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    return await _list_by_source(db, ImageSource.UPLOAD, _request_base(request))


@router.get("/images/approved", response_model=list[ImageInfo])
async def list_approved(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    return await _list_by_source(db, ImageSource.APPROVED, _request_base(request))


@router.get("/images/pending", response_model=list[ImageInfo])
async def list_pending(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    return await _list_by_source(db, ImageSource.GENERATED, _request_base(request))


# ─────────────────────────────────────────────────────────────────────────────
# Delete
# ─────────────────────────────────────────────────────────────────────────────

@router.delete("/images/uploads/{image_id}", response_model=DeleteImageResponse)
async def delete_uploaded(
    image_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    image = await db.get(PosterImage, image_id)
    if image is None:
        raise HTTPException(status_code=404, detail="Image not found")
    if image.source != ImageSource.UPLOAD:
        raise HTTPException(
            status_code=409,
            detail=f"Only uploaded images can be deleted here (source={image.source.value})",
        )
    await image_service.delete_image(db, image)
    return DeleteImageResponse(message="Image deleted")


# ─────────────────────────────────────────────────────────────────────────────
# Approve / Reject
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/images/{image_id}/approve", response_model=ApproveImageResponse)
async def approve_image(
    image_id: UUID,
    request: Request,
    body: ApproveImageRequest,
    db: AsyncSession = Depends(get_db),
):
    image = await db.get(PosterImage, image_id)
    if image is None:
        raise HTTPException(status_code=404, detail="Image not found")

    updated = await image_service.approve_image(
        db=db,
        image=image,
        caption=body.caption,
        platforms=body.platforms,
        scheduled_time=body.scheduled_time,
        request_base=_request_base(request),
    )
    return ApproveImageResponse(
        image_id=str(updated.id),
        approved_url=updated.url,
        message="Image approved",
        scheduled_time=updated.scheduled_time,
    )


@router.post("/images/{image_id}/reject", response_model=RejectImageResponse)
async def reject_image(
    image_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    image = await db.get(PosterImage, image_id)
    if image is None:
        raise HTTPException(status_code=404, detail="Image not found")
    await image_service.reject_image(db, image)
    return RejectImageResponse(image_id=str(image.id), message="Image rejected")
