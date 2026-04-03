# app/services/storage_service.py
# ─────────────────────────────────────────────────────────────────────────────
# AWS S3 operations for poster image storage.
#
# WHY S3 FOR IMAGES?
#   Generated poster images can be 2–5MB each.
#   Storing them in the DB (as BYTEA) would make the DB huge and slow.
#   S3 is cheap (~$0.023/GB/month), durable (99.999999999%), and scales infinitely.
#
# WHAT TO BUILD:
#
#   upload_poster(image_bytes: bytes, brief_id: str, version: int, platform: str) -> str
#       - Key format: posters/{brief_id}/v{version}/{platform}.jpg
#       - Upload to S3_POSTER_BUCKET with ACL=private (NEVER public)
#       - Return the S3 key (not a URL — URLs are generated separately)
#
#   get_presigned_url(s3_key: str, expiry_seconds: int = 3600) -> str
#       - Generate a time-limited pre-signed URL for the review interface
#       - Expiry default = settings.S3_URL_EXPIRY_SECONDS (1 hour from spec §11)
#       - After expiry, the URL stops working — prevents image leaking
#
#   get_cdn_url(s3_key: str) -> str
#       - Only called AFTER a poster is approved
#       - Returns the permanent CloudFront URL for the published post
#       - Format: https://posters.risetechvillage.lk/{s3_key}
#
#   delete_poster_version(brief_id: str, version: int) -> None
#       - Hard-delete all S3 objects for a rejected/exhausted brief version
#       - Clean up storage for content that will never be published
# ─────────────────────────────────────────────────────────────────────────────
