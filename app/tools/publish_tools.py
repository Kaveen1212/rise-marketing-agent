"""
app/tools/publish_tools.py
Platform publishing tools used by the Publisher Agent and background jobs.

Each tool posts content to a specific social media platform via its API.
Uses httpx for HTTP calls with retry logic via tenacity.
"""

from langchain_core.tools import tool
import httpx
import structlog
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

log = structlog.get_logger()


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    retry=retry_if_exception_type((httpx.HTTPStatusError, httpx.ConnectError)),
    reraise=True,
)
def _http_post(url: str, headers: dict, json_body: dict | None = None, data: dict | None = None, timeout: float = 30.0) -> dict:
    """HTTP POST with retry logic."""
    with httpx.Client(timeout=timeout) as client:
        if json_body:
            resp = client.post(url, headers=headers, json=json_body)
        else:
            resp = client.post(url, headers=headers, data=data)
        resp.raise_for_status()
        return resp.json()


@tool
def post_to_instagram(image_url: str, caption: str, hashtags: list[str]) -> str:
    """
    Publish an image post to Instagram via the Meta Graph API.
    Step 1: Create a media container with the image URL.
    Step 2: Publish the container.
    Returns the external post ID assigned by Instagram.
    """
    from app.config import settings

    token = settings.INSTAGRAM_ACCESS_TOKEN
    account_id = settings.INSTAGRAM_BUSINESS_ACCOUNT_ID

    if not token or not account_id:
        log.warning("instagram_not_configured")
        return "instagram_not_configured"

    access_token = token.get_secret_value()
    full_caption = f"{caption}\n\n{' '.join('#' + h for h in hashtags)}" if hashtags else caption

    try:
        # Step 1: Create media container
        container_resp = _http_post(
            f"https://graph.facebook.com/v18.0/{account_id}/media",
            headers={},
            data={
                "image_url": image_url,
                "caption": full_caption,
                "access_token": access_token,
            },
        )
        container_id = container_resp.get("id")
        if not container_id:
            log.error("instagram_no_container_id", response=container_resp)
            return "instagram_container_failed"

        # Step 2: Publish the container
        publish_resp = _http_post(
            f"https://graph.facebook.com/v18.0/{account_id}/media_publish",
            headers={},
            data={
                "creation_id": container_id,
                "access_token": access_token,
            },
        )
        post_id = publish_resp.get("id", "")

        log.info("instagram_posted", post_id=post_id)
        return post_id

    except Exception as e:
        log.error("instagram_post_failed", error=str(e))
        raise


def _get_facebook_page_token(user_token: str, page_id: str) -> str:
    """
    Exchange a user access token for a page-specific access token.
    Required because Facebook Graph API needs 'post as page' token.
    """
    with httpx.Client(timeout=15.0) as client:
        resp = client.get(
            f"https://graph.facebook.com/v18.0/{page_id}",
            params={"fields": "access_token", "access_token": user_token},
        )
        resp.raise_for_status()
        return resp.json().get("access_token", user_token)


@tool
def post_to_facebook(image_url: str, message: str, page_id: str) -> str:
    """
    Publish a photo post to a Facebook Page via the Graph API.
    Uploads the image file directly (multipart) for local images,
    or uses URL for remote images.
    Returns the external post ID.
    """
    from app.config import settings
    from pathlib import Path

    token = settings.FACEBOOK_PAGE_ACCESS_TOKEN
    if not token:
        log.warning("facebook_not_configured")
        return "facebook_not_configured"

    # Get page-specific token (required for posting as the page)
    user_token = token.get_secret_value()
    access_token = _get_facebook_page_token(user_token, page_id)

    try:
        # Check if this is a local file — upload directly via multipart
        if image_url.startswith("http://localhost"):
            local_path = Path(image_url.replace("http://localhost:8000/storage/", "storage/"))
            if not local_path.exists():
                log.error("facebook_local_file_missing", path=str(local_path))
                return "file_not_found"

            with httpx.Client(timeout=60.0) as client:
                with open(local_path, "rb") as img_file:
                    resp = client.post(
                        f"https://graph.facebook.com/v18.0/{page_id}/photos",
                        data={
                            "message": message,
                            "access_token": access_token,
                            "published": "true",
                        },
                        files={"source": (local_path.name, img_file, "image/jpeg")},
                    )
                    resp.raise_for_status()
                    result = resp.json()
        else:
            # Remote URL — use url parameter
            with httpx.Client(timeout=60.0) as client:
                resp = client.post(
                    f"https://graph.facebook.com/v18.0/{page_id}/photos",
                    data={
                        "url": image_url,
                        "message": message,
                        "access_token": access_token,
                        "published": "true",
                    },
                )
                resp.raise_for_status()
                result = resp.json()

        post_id = result.get("id", result.get("post_id", ""))
        log.info("facebook_posted", post_id=post_id, page_id=page_id)
        return post_id

    except Exception as e:
        log.error("facebook_post_failed", error=str(e))
        raise


@tool
def post_to_linkedin(image_url: str, text: str, org_id: str) -> str:
    """
    Publish an image post to a LinkedIn Organisation page via the API.
    Uses the UGC Post API for image sharing.
    Returns the external post URN.
    """
    from app.config import settings

    token = settings.LINKEDIN_ACCESS_TOKEN
    if not token or not org_id:
        log.warning("linkedin_not_configured")
        return "linkedin_not_configured"

    access_token = token.get_secret_value()
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
        "X-Restli-Protocol-Version": "2.0.0",
    }

    try:
        # Step 1: Register image upload
        register_resp = _http_post(
            "https://api.linkedin.com/v2/assets?action=registerUpload",
            headers=headers,
            json_body={
                "registerUploadRequest": {
                    "recipes": ["urn:li:digitalmediaRecipe:feedshare-image"],
                    "owner": f"urn:li:organization:{org_id}",
                    "serviceRelationships": [{
                        "relationshipType": "OWNER",
                        "identifier": "urn:li:userGeneratedContent",
                    }],
                }
            },
        )

        asset = register_resp.get("value", {}).get("asset", "")

        # Step 2: Create the UGC post with the image
        post_resp = _http_post(
            "https://api.linkedin.com/v2/ugcPosts",
            headers=headers,
            json_body={
                "author": f"urn:li:organization:{org_id}",
                "lifecycleState": "PUBLISHED",
                "specificContent": {
                    "com.linkedin.ugc.ShareContent": {
                        "shareCommentary": {"text": text},
                        "shareMediaCategory": "IMAGE",
                        "media": [{
                            "status": "READY",
                            "description": {"text": text[:200]},
                            "media": asset or image_url,
                            "originalUrl": image_url,
                        }],
                    }
                },
                "visibility": {
                    "com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"
                },
            },
        )

        post_urn = post_resp.get("id", "")
        log.info("linkedin_posted", post_urn=post_urn)
        return post_urn

    except Exception as e:
        log.error("linkedin_post_failed", error=str(e))
        raise


@tool
def post_to_tiktok(video_url: str, caption: str) -> str:
    """
    Initiate a TikTok post via the Content Posting API.
    Note: TikTok requires video content. For image posters, a slideshow
    video must be pre-generated. Returns the publish_id for tracking.
    """
    from app.config import settings

    client_key = settings.TIKTOK_CLIENT_KEY
    client_secret = settings.TIKTOK_CLIENT_SECRET

    if not client_key or not client_secret:
        log.warning("tiktok_not_configured")
        return "tiktok_not_configured"

    try:
        # TikTok requires OAuth2 access token first
        token_resp = _http_post(
            "https://open.tiktokapis.com/v2/oauth/token/",
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            data={
                "client_key": client_key.get_secret_value(),
                "client_secret": client_secret.get_secret_value(),
                "grant_type": "client_credentials",
            },
        )

        access_token = token_resp.get("access_token", "")
        if not access_token:
            log.error("tiktok_auth_failed", response=token_resp)
            return "tiktok_auth_failed"

        # Initiate video publish
        publish_resp = _http_post(
            "https://open.tiktokapis.com/v2/post/publish/video/init/",
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
            },
            json_body={
                "post_info": {
                    "title": caption[:150],
                    "privacy_level": "PUBLIC_TO_EVERYONE",
                    "disable_comment": False,
                    "disable_duet": False,
                    "disable_stitch": False,
                },
                "source_info": {
                    "source": "PULL_FROM_URL",
                    "video_url": video_url,
                },
            },
        )

        publish_id = publish_resp.get("data", {}).get("publish_id", "")
        log.info("tiktok_publish_initiated", publish_id=publish_id)
        return publish_id

    except Exception as e:
        log.error("tiktok_post_failed", error=str(e))
        raise


@tool
def calculate_optimal_schedule(platform: str, override_datetime: str | None) -> str:
    """
    Calculate the optimal publish time for a Sri Lankan audience.
    Returns an ISO 8601 datetime string in UTC.
    Sri Lanka is UTC+5:30. Peak times: Instagram 8pm, Facebook 7:30pm, LinkedIn 7pm, TikTok 9pm IST.
    """
    from datetime import datetime, timezone, timedelta
    IST = timezone(timedelta(hours=5, minutes=30))

    if override_datetime:
        return override_datetime

    peak_hours = {
        "instagram": (20, 0),   # 8:00 pm
        "facebook":  (19, 30),  # 7:30 pm
        "linkedin":  (19, 0),   # 7:00 pm
        "tiktok":    (21, 0),   # 9:00 pm
    }
    hour, minute = peak_hours.get(platform, (20, 0))
    now = datetime.now(IST)
    publish_ist = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if publish_ist <= now:
        publish_ist += timedelta(days=1)
    return publish_ist.astimezone(timezone.utc).isoformat()
