"""
app/services/publish_service.py
─────────────────────────────────────────────────────────────────────────────
Scheduling logic and analytics collection for the Publisher Agent (Agent 5).

Responsibilities:
  1. calculate_publish_time() — decide WHEN a post goes live (Sri Lanka peak hours)
  2. schedule_post()          — write a row to poster_publications (status=scheduled)
  3. publish_due_posts()      — background job: push scheduled posts to platforms
  4. collect_due_analytics()  — background job: fetch 24h stats from platform APIs

How the background jobs work (no Celery needed):
  APScheduler runs inside FastAPI's lifespan context.
  publish_due_posts()     → runs every 60 seconds
  collect_due_analytics() → runs every 5 minutes
  Both jobs are registered in app/main.py.
─────────────────────────────────────────────────────────────────────────────
"""

import structlog
from datetime import datetime, timedelta, timezone

import httpx
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import AsyncSessionLocal
from app.models.publication import PosterPublication, PublicationStatus

log = structlog.get_logger()

# ─────────────────────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────────────────────

# Sri Lanka Standard Time is UTC+5:30 — no daylight saving
SRI_LANKA_TZ = timezone(timedelta(hours=5, minutes=30))

# Peak publish hours per platform (hour, minute) in Sri Lanka local time
# Values come from config so they can be overridden without code changes
PLATFORM_PEAK_TIMES: dict[str, tuple[int, int]] = {
    "instagram": (settings.PUBLISH_HOUR_INSTAGRAM, 0),
    "facebook":  (settings.PUBLISH_HOUR_FACEBOOK,  settings.PUBLISH_MINUTE_FACEBOOK),
    "linkedin":  (settings.PUBLISH_HOUR_LINKEDIN_PM, 0),
    "tiktok":    (settings.PUBLISH_HOUR_TIKTOK, 0),
}


# ─────────────────────────────────────────────────────────────────────────────
# 1. calculate_publish_time
# ─────────────────────────────────────────────────────────────────────────────

def calculate_publish_time(
    platform: str,
    override: datetime | None = None,
) -> datetime:
    """
    Return a timezone-aware UTC datetime for when the post should go live.

    If the reviewer supplied a schedule_override, use that directly.
    Otherwise, pick today's peak hour for the platform in Sri Lanka time.
    If that time has already passed today, schedule for tomorrow.

    Args:
        platform: One of instagram / facebook / linkedin / tiktok
        override: Optional reviewer-specified datetime (must be tz-aware)

    Returns:
        UTC datetime for the scheduled publish time
    """
    if override is not None:
        # Reviewer explicitly chose a time — convert to UTC and honour it
        return override.astimezone(timezone.utc)

    hour, minute = PLATFORM_PEAK_TIMES.get(platform, (20, 0))

    # What time is it right now in Sri Lanka?
    now_sl = datetime.now(SRI_LANKA_TZ)

    # Build today's target time in Sri Lanka timezone
    target_sl = now_sl.replace(
        hour=hour,
        minute=minute,
        second=0,
        microsecond=0,
    )

    # If the window already passed today, push to the same time tomorrow
    if target_sl <= now_sl:
        target_sl += timedelta(days=1)

    # Always store as UTC in the database
    return target_sl.astimezone(timezone.utc)


# ─────────────────────────────────────────────────────────────────────────────
# 2. schedule_post
# ─────────────────────────────────────────────────────────────────────────────

async def schedule_post(
    db: AsyncSession,
    brief_id: str,
    version_id: str,
    platform: str,
    language: str,
    publish_time: datetime,
) -> str:
    """
    Create a poster_publications row with status=scheduled.

    Called by the publisher_agent (Agent 5) once per platform × language
    combination after human approval.

    Example: brief targeting [instagram, facebook] × [en, si]
    → 4 calls to schedule_post() → 4 rows in poster_publications

    Args:
        db:           SQLAlchemy async session
        brief_id:     UUID of the parent poster_briefs row
        version_id:   UUID of the approved poster_versions row
        platform:     Target platform: instagram / facebook / linkedin / tiktok
        language:     Language variant: en / si / ta
        publish_time: UTC datetime from calculate_publish_time()

    Returns:
        String UUID of the newly created poster_publications row
    """
    pub = PosterPublication(
        brief_id=brief_id,
        version_id=version_id,
        platform=platform,
        language=language,
        scheduled_at=publish_time,
        status=PublicationStatus.SCHEDULED,
    )
    db.add(pub)

    # flush() sends the INSERT inside the current transaction so we get the
    # auto-generated UUID back — without committing yet.
    # The session commits automatically when the request ends (see database.py).
    await db.flush()

    log.info(
        "post_scheduled",
        publication_id=str(pub.id),
        platform=platform,
        language=language,
        scheduled_at=publish_time.isoformat(),
    )

    return str(pub.id)


# ─────────────────────────────────────────────────────────────────────────────
# 3. publish_due_posts  (APScheduler job — runs every 60 seconds)
# ─────────────────────────────────────────────────────────────────────────────

async def publish_due_posts() -> None:
    """
    Background job: find every poster_publications row that is due to go live
    and publish it to the appropriate platform via the platform API.

    Runs on a 60-second interval via APScheduler (registered in main.py).

    Flow per due row:
      1. Call the platform API
      2. Store the external_post_id returned by the platform
      3. Mark status = published, record published_at timestamp
      4. On failure: mark status = failed and log — retries on next tick
    """
    now_utc = datetime.now(timezone.utc)

    try:
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(PosterPublication).where(
                    and_(
                        PosterPublication.status == PublicationStatus.SCHEDULED,
                        PosterPublication.scheduled_at <= now_utc,
                    )
                )
            )
            due_posts = result.scalars().all()

            if not due_posts:
                return

            log.info("publish_job_running", due_count=len(due_posts))

            for pub in due_posts:
                try:
                    post_id = await _call_platform_api(pub)
                    pub.external_post_id = post_id
                    pub.status = PublicationStatus.PUBLISHED
                    pub.published_at = datetime.now(timezone.utc)

                    log.info(
                        "post_published",
                        publication_id=str(pub.id),
                        platform=pub.platform,
                        external_post_id=post_id,
                    )

                except Exception as exc:
                    pub.status = PublicationStatus.FAILED
                    log.error(
                        "post_publish_failed",
                        publication_id=str(pub.id),
                        platform=pub.platform,
                        error=str(exc),
                    )

            await db.commit()

    except OSError as exc:
        log.warning("publish_job_skipped_db_unavailable", error=str(exc))
    except Exception as exc:
        log.error("publish_job_error", error=str(exc))


# ─────────────────────────────────────────────────────────────────────────────
# 4. collect_due_analytics  (APScheduler job — runs every 5 minutes)
# ─────────────────────────────────────────────────────────────────────────────

async def collect_due_analytics() -> None:
    """
    Background job: for every published post that is at least 24 hours old
    and has not yet had analytics fetched, call the platform API and store
    the engagement numbers.

    Runs every 5 minutes via APScheduler (registered in main.py).

    Updates poster_publications with:
      - reach_24h
      - engagements_24h
      - followers_gained_24h
      - analytics_fetched_at
    """
    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)

    try:
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(PosterPublication).where(
                    and_(
                        PosterPublication.status == PublicationStatus.PUBLISHED,
                        PosterPublication.analytics_fetched_at.is_(None),
                        PosterPublication.published_at <= cutoff,
                    )
                )
            )
            due_analytics = result.scalars().all()

            if not due_analytics:
                return

            log.info("analytics_job_running", due_count=len(due_analytics))

            for pub in due_analytics:
                try:
                    stats = await _fetch_platform_analytics(pub)
                    pub.reach_24h = stats.get("reach", 0)
                    pub.engagements_24h = stats.get("engagements", 0)
                    pub.followers_gained_24h = stats.get("followers_gained", 0)
                    pub.analytics_fetched_at = datetime.now(timezone.utc)

                    log.info(
                        "analytics_collected",
                        publication_id=str(pub.id),
                        platform=pub.platform,
                        reach=pub.reach_24h,
                        engagements=pub.engagements_24h,
                    )

                except Exception as exc:
                    log.warning(
                        "analytics_fetch_failed",
                        publication_id=str(pub.id),
                        platform=pub.platform,
                        error=str(exc),
                    )

            await db.commit()

    except OSError as exc:
        log.warning("analytics_job_skipped_db_unavailable", error=str(exc))
    except Exception as exc:
        log.error("analytics_job_error", error=str(exc))


# ─────────────────────────────────────────────────────────────────────────────
# Internal helpers — platform routing
# ─────────────────────────────────────────────────────────────────────────────

async def _call_platform_api(pub: PosterPublication) -> str:
    """
    Route to the correct platform publish tool based on pub.platform.
    Loads the poster version to get copy and hashtags for the caption.
    Returns the external_post_id string from the platform.
    """
    from app.tools.publish_tools import (
        post_to_facebook,
        post_to_instagram,
        post_to_linkedin,
        post_to_tiktok,
    )

    image_url = await _resolve_image_url(pub)

    # Load version data for caption text
    caption = ""
    hashtags = []
    async with AsyncSessionLocal() as db:
        from app.models.version import PosterVersion
        from app.models.brief import PosterBrief
        version = await db.get(PosterVersion, pub.version_id)
        brief = await db.get(PosterBrief, pub.brief_id)
        if version:
            lang = pub.language
            headline = version.headline.get(lang, "")
            body = version.body_copy.get(lang, "")
            cta = version.cta.get(lang, "")
            platform_hashtags = version.hashtags.get(pub.platform, [])
            hashtag_str = " ".join(f"#{h}" for h in platform_hashtags) if platform_hashtags else ""
            caption = f"{headline}\n\n{body}\n\n{cta}\n\n{hashtag_str}".strip()
            hashtags = platform_hashtags if platform_hashtags else []

    if pub.platform == "instagram":
        return post_to_instagram.invoke({
            "image_url": image_url,
            "caption": caption,
            "hashtags": hashtags,
        })
    elif pub.platform == "facebook":
        return post_to_facebook.invoke({
            "image_url": image_url,
            "message": caption,
            "page_id": settings.FACEBOOK_PAGE_ID,
        })
    elif pub.platform == "linkedin":
        return post_to_linkedin.invoke({
            "image_url": image_url,
            "text": caption,
            "org_id": settings.LINKEDIN_ORG_ID,
        })
    elif pub.platform == "tiktok":
        return post_to_tiktok.invoke({
            "video_url": image_url,
            "caption": caption,
        })
    else:
        raise ValueError(f"Unknown platform: {pub.platform}")


async def _fetch_platform_analytics(pub: PosterPublication) -> dict:
    """
    Dispatch analytics fetch to the right platform-specific function.
    Returns dict with keys: reach, engagements, followers_gained.
    """
    if pub.platform == "instagram":
        return await _instagram_analytics(pub.external_post_id)
    elif pub.platform == "facebook":
        return await _facebook_analytics(pub.external_post_id)

    # LinkedIn and TikTok analytics require separate OAuth — return zeros for now
    return {"reach": 0, "engagements": 0, "followers_gained": 0}


async def _instagram_analytics(post_id: str) -> dict:
    """
    Fetch Instagram insights via the Graph API.
    Metrics: reach, engagement (likes + comments + saves).
    """
    token = settings.INSTAGRAM_ACCESS_TOKEN
    if not token:
        return {"reach": 0, "engagements": 0, "followers_gained": 0}

    url = (
        f"https://graph.facebook.com/v18.0/{post_id}/insights"
        f"?metric=impressions,reach,engagement"
        f"&access_token={token.get_secret_value()}"
    )

    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.get(url)
        response.raise_for_status()
        data = response.json().get("data", [])

    metrics = {item["name"]: item["values"][0]["value"] for item in data}
    return {
        "reach":            metrics.get("reach", 0),
        "engagements":      metrics.get("engagement", 0),
        # Instagram does not expose per-post follower gain via the insights API
        "followers_gained": 0,
    }


async def _facebook_analytics(post_id: str) -> dict:
    """
    Fetch Facebook post insights via the Graph API.
    Metrics: post_impressions_unique (reach), post_engaged_users (engagements).
    """
    token = settings.FACEBOOK_PAGE_ACCESS_TOKEN
    if not token:
        return {"reach": 0, "engagements": 0, "followers_gained": 0}

    url = (
        f"https://graph.facebook.com/v18.0/{post_id}/insights"
        f"?metric=post_impressions_unique,post_engaged_users"
        f"&access_token={token.get_secret_value()}"
    )

    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.get(url)
        response.raise_for_status()
        data = response.json().get("data", [])

    metrics = {item["name"]: item["values"][0]["value"] for item in data}
    return {
        "reach":            metrics.get("post_impressions_unique", 0),
        "engagements":      metrics.get("post_engaged_users", 0),
        "followers_gained": 0,
    }


async def _resolve_image_url(pub: PosterPublication) -> str:
    """
    Get the platform-specific poster image URL from the version record.
    poster_urls shape: {"instagram": "https://...", "facebook": "https://..."}
    Falls back to the base image_url if the platform variant is missing.
    """
    async with AsyncSessionLocal() as db:
        from app.models.version import PosterVersion
        version = await db.get(PosterVersion, pub.version_id)
        if version and version.poster_urls:
            return version.poster_urls.get(pub.platform, version.image_url)
        if version:
            return version.image_url
    return ""
