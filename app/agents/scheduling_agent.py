"""
app/agents/scheduling_agent.py
─────────────────────────────────────────────────────────────────────────────
AI-powered social media scheduling agent.

Replaces the deterministic peak-hour lookup with a Claude-powered agent
that reasons about optimal posting times based on:
  - Platform characteristics
  - Campaign topic and urgency
  - Target audience behavior patterns
  - Current day and time in Sri Lanka (UTC+5:30)
─────────────────────────────────────────────────────────────────────────────
"""

import json
import structlog
from datetime import datetime, timedelta, timezone

log = structlog.get_logger()

# Sri Lanka timezone: UTC+5:30
SRI_LANKA_OFFSET = timezone(timedelta(hours=5, minutes=30))

# Deterministic fallback peak hours (IST 24h)
PLATFORM_PEAK_HOURS = {
    "instagram": {"hour": 20, "minute": 0},   # 8:00 PM
    "facebook":  {"hour": 19, "minute": 30},  # 7:30 PM
    "linkedin":  {"hour": 9,  "minute": 0},   # 9:00 AM (professionals)
    "tiktok":    {"hour": 21, "minute": 0},   # 9:00 PM
}


def _get_fallback_time(platform: str) -> str:
    """Deterministic fallback: next platform peak hour in IST."""
    now_ist = datetime.now(SRI_LANKA_OFFSET)
    peak = PLATFORM_PEAK_HOURS.get(platform, PLATFORM_PEAK_HOURS["instagram"])

    target = now_ist.replace(
        hour=peak["hour"],
        minute=peak["minute"],
        second=0,
        microsecond=0,
    )

    # If peak has passed today, schedule for tomorrow
    if target <= now_ist:
        target += timedelta(days=1)

    hour = target.strftime("%I").lstrip("0") or "12"
    return target.strftime(f"%A, %B %d at {hour}:%M %p IST")


def get_suggested_post_time(
    platform: str,
    topic: str = "",
    audience: str = "general",
) -> str:
    """
    Use Claude to recommend the optimal posting time for a campaign.
    Falls back to deterministic peak hours if Claude is unavailable.

    Returns a human-readable string like "Tuesday, April 15 at 8:00 PM IST"
    """
    try:
        from app.config import settings
        import anthropic

        client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY.get_secret_value())

        now_ist = datetime.now(SRI_LANKA_OFFSET)
        day_name = now_ist.strftime("%A")
        current_time = now_ist.strftime("%I:%M %p")
        peak = PLATFORM_PEAK_HOURS.get(platform, PLATFORM_PEAK_HOURS["instagram"])

        system_prompt = """You are a social media scheduling specialist for Sri Lanka (UTC+5:30).
Given campaign details, recommend the single best publish time for maximum engagement.

Return ONLY valid JSON: {"recommended_time": "YYYY-MM-DDTHH:MM:SS", "reasoning": "one sentence"}

Rules:
- Platform instagram baseline: 8:00 PM IST
- Platform facebook baseline: 7:30 PM IST
- Platform linkedin baseline: 9:00 AM IST (professionals check LinkedIn mornings)
- Platform tiktok baseline: 9:00 PM IST
- Students (18-25): 6-9 PM IST weekdays, 11 AM-1 PM weekends
- Professionals: 8-9 AM or 6-8 PM IST weekdays
- For event promotions (workshops, bootcamps): post 3-5 days before event
- Stay within ±2 hours of baseline unless strong campaign reason
- Never schedule more than 7 days out
- If today's window has passed, use tomorrow's baseline"""

        user_message = f"""Platform: {platform}
Campaign topic: {topic or "general marketing content"}
Target audience: {audience}
Current time in Sri Lanka: {day_name} {current_time} IST
Current datetime ISO: {now_ist.isoformat()}

What is the best time to publish this content?"""

        response = client.messages.create(
            model=settings.ANTHROPIC_MODEL,
            max_tokens=256,
            system=system_prompt,
            messages=[{"role": "user", "content": user_message}],
        )

        text = response.content[0].text.strip()
        # Strip markdown fences
        if text.startswith("```"):
            lines = text.split("\n")
            text = "\n".join(lines[1:-1])

        data = json.loads(text)
        recommended = datetime.fromisoformat(data["recommended_time"])

        # Make timezone-aware if Claude returned a naive datetime
        if recommended.tzinfo is None:
            recommended = recommended.replace(tzinfo=SRI_LANKA_OFFSET)

        # Clamp: must be in the future, no more than 7 days out
        if recommended <= now_ist:
            return _get_fallback_time(platform)
        if recommended > now_ist + timedelta(days=7):
            return _get_fallback_time(platform)

        hour = recommended.strftime("%I").lstrip("0") or "12"
        return recommended.strftime(f"%A, %B %d at {hour}:%M %p IST")

    except Exception as e:
        log.warning("scheduling_agent_fallback", error=str(e), platform=platform)
        return _get_fallback_time(platform)


def get_schedule_for_platforms(
    platforms: list[str],
    topic: str = "",
    audience: str = "general",
) -> dict[str, str]:
    """
    Get suggested posting times for multiple platforms.
    Returns a dict of platform -> suggested time string.
    """
    return {
        platform: get_suggested_post_time(platform, topic, audience)
        for platform in platforms
    }
