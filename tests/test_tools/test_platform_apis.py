# tests/test_tools/test_platform_apis.py
# ─────────────────────────────────────────────────────────────────────────────
# Spec §7.3 Stage 4: "Verify all 4 platform publish functions with mock responses"
#
# TESTS TO WRITE:
#
#   test_post_to_instagram_success()
#       - Mock httpx to return a fake IG API response: { "id": "12345" }
#       - Call publish_tools.post_to_instagram(poster_url, caption, hashtags)
#       - Assert: returns the post id "12345"
#
#   test_post_to_facebook_success() — same pattern
#
#   test_post_to_linkedin_success() — same pattern
#
#   test_post_to_tiktok_success() — same pattern
#
#   test_platform_api_rate_limit_retries()
#       - Mock httpx to return 429 (rate limit) twice, then 200
#       - Assert: publish_tools retries with exponential backoff
#       - Assert: eventually succeeds on 3rd attempt (spec §11 — retry up to 3 times)
#
#   test_platform_api_down_queues_gracefully()
#       - Mock httpx to always return 503
#       - Assert: post status remains "scheduled" (not "failed") until retry limit
# ─────────────────────────────────────────────────────────────────────────────
