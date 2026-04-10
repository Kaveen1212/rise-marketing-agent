# app/services/storage_service.py
# ─────────────────────────────────────────────────────────────────────────────
# Local file storage for poster images (development mode).
# In production, switch to AWS S3 by setting USE_LOCAL_STORAGE=false.
# ─────────────────────────────────────────────────────────────────────────────

import os
import uuid
from pathlib import Path

from app.config import settings

# Local storage directory — created at app root
STORAGE_DIR = Path("storage/posters")


def _ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def upload_poster(image_bytes: bytes, brief_id: str, version: int, platform: str) -> str:
    """
    Save poster image to local storage.
    Returns the relative file path (used as the storage key).
    """
    key = f"posters/{brief_id}/v{version}/{platform}.jpg"
    file_path = STORAGE_DIR / brief_id / f"v{version}"
    _ensure_dir(file_path)
    full_path = file_path / f"{platform}.jpg"
    full_path.write_bytes(image_bytes)
    return key


def get_presigned_url(storage_key: str, expiry_seconds: int = 3600) -> str:
    """
    In local mode, return a URL served by FastAPI's static files.
    In production, this would generate an S3 pre-signed URL.
    """
    return f"http://localhost:8000/storage/{storage_key}"


def get_cdn_url(storage_key: str) -> str:
    """
    In local mode, same as presigned URL.
    In production, returns the CloudFront URL.
    """
    return f"http://localhost:8000/storage/{storage_key}"


def delete_poster_version(brief_id: str, version: int) -> None:
    """
    Delete all files for a rejected/exhausted poster version.
    """
    version_dir = STORAGE_DIR / brief_id / f"v{version}"
    if version_dir.exists():
        import shutil
        shutil.rmtree(version_dir)
