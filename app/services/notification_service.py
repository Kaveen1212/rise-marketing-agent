# app/services/notification_service.py
# ─────────────────────────────────────────────────────────────────────────────
# Sends Slack and email notifications at key pipeline events.
# Spec §7.2: REVIEW_SLACK_CHANNEL, REVIEW_NOTIFICATION_EMAIL
#
# WHAT TO BUILD:
#
#   notify_pending_review(brief: PosterBrief, poster_url: str) -> None
#       - Triggered: when QA Agent passes a poster (status → pending_review)
#       - Slack: Post to #poster-review-queue with poster thumbnail + review link
#       - Email: Send to REVIEW_NOTIFICATION_EMAIL with the same info
#       - Must fire within 30 seconds of QA pass (spec §9.2 exit criteria)
#
#   notify_approved(brief: PosterBrief) -> None
#       - Triggered: when reviewer approves
#       - Slack: Post to #poster-review-queue confirming approval + schedule time
#
#   notify_rejected(brief: PosterBrief, reason: str) -> None
#       - Triggered: when reviewer rejects OR poster is exhausted (3 revision cycles)
#       - Slack: Notify channel + DM the original brief submitter
#       - Email: Notify the marketing coordinator to resubmit the brief
#
# HOW SLACK WEBHOOKS WORK:
#   POST JSON to settings.REVIEW_SLACK_WEBHOOK_URL with:
#   { "text": "...", "blocks": [...] }
#   Use httpx.AsyncClient for async HTTP calls.
# ─────────────────────────────────────────────────────────────────────────────
