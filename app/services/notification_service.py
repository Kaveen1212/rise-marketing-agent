"""
app/services/notification_service.py
Sends Slack and email notifications at key pipeline events.
Spec S7.2: REVIEW_SLACK_CHANNEL, REVIEW_NOTIFICATION_EMAIL

All notification functions are fire-and-forget — failures are logged
but never block the pipeline.
"""

import structlog
import httpx

from app.config import settings

log = structlog.get_logger()


async def _post_to_slack(blocks: list[dict], text: str) -> None:
    """
    Send a message to the configured Slack webhook.
    Falls back to text-only if blocks fail.
    """
    webhook_url = settings.REVIEW_SLACK_WEBHOOK_URL
    if not webhook_url:
        log.warning("slack_webhook_not_configured")
        return

    payload = {
        "channel": settings.REVIEW_SLACK_CHANNEL,
        "text": text,
        "blocks": blocks,
    }

    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(
            webhook_url.get_secret_value(),
            json=payload,
        )
        if resp.status_code != 200:
            log.warning("slack_webhook_failed", status=resp.status_code, body=resp.text)
        else:
            log.info("slack_notification_sent")


async def notify_pending_review(brief, poster_url: str | None = None) -> None:
    """
    Triggered when QA Agent passes a poster (status -> pending_review).
    Posts to #poster-review-queue with poster info + review link.
    """
    review_link = f"http://localhost:3000/review/{brief.id}"

    text = (
        f"New poster ready for review: *{brief.topic}*\n"
        f"Platforms: {', '.join(brief.platforms)}\n"
        f"Languages: {', '.join(brief.languages)}\n"
        f"<{review_link}|Open Review Interface>"
    )

    blocks = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": "Poster Ready for Review"},
        },
        {
            "type": "section",
            "fields": [
                {"type": "mrkdwn", "text": f"*Topic:*\n{brief.topic}"},
                {"type": "mrkdwn", "text": f"*Platforms:*\n{', '.join(brief.platforms)}"},
                {"type": "mrkdwn", "text": f"*Languages:*\n{', '.join(brief.languages)}"},
                {"type": "mrkdwn", "text": f"*Revision:*\n#{brief.revision_count}"},
            ],
        },
        {
            "type": "actions",
            "elements": [
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "Review Now"},
                    "url": review_link,
                    "style": "primary",
                },
            ],
        },
    ]

    try:
        await _post_to_slack(blocks, text)
    except Exception as e:
        log.warning("notify_pending_review_failed", error=str(e))


async def notify_approved(brief) -> None:
    """
    Triggered when reviewer approves a poster.
    Posts confirmation to #poster-review-queue with schedule info.
    """
    from app.services.publish_service import calculate_publish_time

    schedule_info = []
    for platform in brief.platforms:
        pt = calculate_publish_time(platform)
        schedule_info.append(f"{platform}: {pt.strftime('%Y-%m-%d %H:%M UTC')}")

    text = (
        f"Poster approved: *{brief.topic}*\n"
        f"Scheduled: {', '.join(schedule_info)}"
    )

    blocks = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": "Poster Approved"},
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*{brief.topic}* has been approved and scheduled for publication.",
            },
        },
        {
            "type": "section",
            "fields": [
                {"type": "mrkdwn", "text": f"*{s.split(':')[0]}:*\n{':'.join(s.split(':')[1:])}"}
                for s in schedule_info
            ],
        },
    ]

    try:
        await _post_to_slack(blocks, text)
    except Exception as e:
        log.warning("notify_approved_failed", error=str(e))


async def notify_rejected(brief, reason: str) -> None:
    """
    Triggered when reviewer rejects a poster or poster is exhausted.
    Posts to #poster-review-queue and notifies the coordinator.
    """
    text = (
        f"Poster rejected: *{brief.topic}*\n"
        f"Reason: {reason}\n"
        f"Brief must be resubmitted as a new campaign."
    )

    blocks = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": "Poster Rejected"},
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    f"*{brief.topic}* has been rejected.\n\n"
                    f"*Reason:* {reason}\n\n"
                    f"Submitted by: `{brief.submitted_by}`\n"
                    f"Revisions attempted: {brief.revision_count}\n\n"
                    f"The brief must be resubmitted as a new campaign."
                ),
            },
        },
    ]

    try:
        await _post_to_slack(blocks, text)
    except Exception as e:
        log.warning("notify_rejected_failed", error=str(e))


async def notify_published(brief, platform: str, post_id: str) -> None:
    """
    Triggered when a scheduled post goes live on a platform.
    """
    text = f"Poster published: *{brief.topic}* on {platform} (post ID: {post_id})"

    blocks = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": "Poster Published"},
        },
        {
            "type": "section",
            "fields": [
                {"type": "mrkdwn", "text": f"*Topic:*\n{brief.topic}"},
                {"type": "mrkdwn", "text": f"*Platform:*\n{platform}"},
                {"type": "mrkdwn", "text": f"*Post ID:*\n{post_id}"},
            ],
        },
    ]

    try:
        await _post_to_slack(blocks, text)
    except Exception as e:
        log.warning("notify_published_failed", error=str(e))
