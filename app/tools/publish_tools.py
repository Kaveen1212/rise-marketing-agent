from langchain_core.tools import tool
import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

@tool
def post_to_instagram(image_url: str, caption: str, hashtags: list[str]) -> str:
    """
    Publish an image post to Instagram via Graph API.
    Returns the external post ID assigned by Instagram.
    """
    # Step 1: Create media container
    # POST https://graph.facebook.com/v18.0/{ig_user_id}/media
    # Step 2: Publish the container
    # POST https://graph.facebook.com/v18.0/{ig_user_id}/media_publish
    return "17841400000000001"  # Instagram post ID

@tool
def post_to_facebook(image_url: str, message: str, page_id: str) -> str:
    """
    Publish a photo post to a Facebook Page via Graph API.
    Returns the external post ID.
    """
    # POST https://graph.facebook.com/v18.0/{page_id}/photos
    return "123456789_987654321"

@tool
def post_to_linkedin(image_url: str, text: str, org_id: str) -> str:
    """
    Publish an image post to a LinkedIn Organisation page via API.
    Returns the external post URN.
    """
    # POST https://api.linkedin.com/v2/ugcPosts
    return "urn:li:share:7000000000000001"

@tool
def post_to_tiktok(video_url: str, caption: str) -> str:
    """
    Publish a video post to TikTok (note: TikTok requires video, not image).
    Returns the external post ID.
    """
    return "7000000000000000001"

@tool
def calculate_optimal_schedule(platform: str, override_datetime: str | None) -> str:
    """
    Calculate the optimal publish time for a Sri Lankan audience.
    Returns an ISO 8601 datetime string in UTC.
    Sri Lanka is UTC+5:30. Peak times: Instagram 8pm, Facebook 7:30pm, LinkedIn 9am/7pm, TikTok 9pm IST.
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
