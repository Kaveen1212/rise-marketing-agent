# tests/test_api/test_review.py
# ─────────────────────────────────────────────────────────────────────────────
# API-level tests for the /poster/review endpoints.
#
# TESTS TO WRITE:
#
#   test_review_endpoints_require_reviewer_role()
#       - POST /poster/review/{id}/approve with staff_token (not reviewer)
#       - Assert: 403 Forbidden
#
#   test_approve_with_scores_below_threshold()
#       - POST approve with average score = 3.0 (below 3.5 threshold)
#       - Assert: 422 (schema validation rejects it before even hitting DB)
#
#   test_approve_with_critical_fail_score()
#       - POST approve where score_brand = 1 (critical fail)
#       - Assert: 422 (any score of 1 blocks approval)
#
#   test_approve_requires_all_four_scores()
#       - POST approve with only 2 scores provided
#       - Assert: 422
#
#   test_revise_requires_feedback()
#       - POST revise with feedback="" (empty)
#       - Assert: 422
#
#   test_reject_requires_reason()
#       - POST reject without reject_reason
#       - Assert: 422
# ─────────────────────────────────────────────────────────────────────────────
