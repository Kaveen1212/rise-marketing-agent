"""
app/agents/publisher.py
Agent 5 — Publisher Agent

Runs after human approval. For each platform x language combination,
calculates the optimal Sri Lanka peak-hour publish time and creates
a poster_publications row (status=scheduled).

Unlike other agents, this one does NOT use an LLM — it is purely
deterministic scheduling logic.
"""

import asyncio
import structlog

from app.graph.state import PosterState
from app.database import AsyncSessionLocal
from app.services.publish_service import calculate_publish_time, schedule_post
from app.models.version import PosterVersion
from app.models.brief import PosterBrief, PosterStatus

from sqlalchemy import select

log = structlog.get_logger()


async def _schedule_all(state: PosterState) -> dict:
    """Async helper that does the actual DB work."""
    brief_id = state["brief_id"]
    platforms = state["platforms"]
    languages = state["languages"]

    log.info(
        "publisher_agent_running",
        brief_id=brief_id,
        platforms=platforms,
        languages=languages,
    )

    scheduled_at = {}
    publication_ids = {}

    async with AsyncSessionLocal() as db:
        # Find the latest approved version
        result = await db.execute(
            select(PosterVersion)
            .where(PosterVersion.brief_id == brief_id)
            .order_by(PosterVersion.version_number.desc())
            .limit(1)
        )
        latest_version = result.scalar_one_or_none()

        if latest_version is None:
            log.error("publisher_no_version_found", brief_id=brief_id)
            return {
                "scheduled_at": {},
                "published_post_ids": {},
                "analytics_24h": {},
            }

        version_id = str(latest_version.id)

        # Schedule one publication per platform x language
        for platform in platforms:
            publish_time = calculate_publish_time(platform)
            scheduled_at[platform] = publish_time.isoformat()

            for language in languages:
                pub_id = await schedule_post(
                    db=db,
                    brief_id=brief_id,
                    version_id=version_id,
                    platform=platform,
                    language=language,
                    publish_time=publish_time,
                )
                publication_ids[f"{platform}_{language}"] = pub_id

        # Update brief status to scheduled
        brief = await db.get(PosterBrief, brief_id)
        if brief:
            brief.status = PosterStatus.SCHEDULED
            await db.flush()

        await db.commit()

    log.info(
        "publisher_agent_done",
        brief_id=brief_id,
        scheduled_count=len(publication_ids),
        scheduled_at=scheduled_at,
    )

    return {
        "scheduled_at": scheduled_at,
        "published_post_ids": publication_ids,
        "analytics_24h": {},
    }


def publisher_agent(state: PosterState) -> dict:
    """
    LangGraph node — schedules approved poster for publication.
    Wraps the async logic so it works with both sync and async graph execution.
    """
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        # We're inside an async context — create a new thread to run async code
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor() as pool:
            return pool.submit(asyncio.run, _schedule_all(state)).result()
    else:
        return asyncio.run(_schedule_all(state))
