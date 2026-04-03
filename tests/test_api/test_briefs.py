# tests/test_api/test_briefs.py
# ─────────────────────────────────────────────────────────────────────────────
# API-level tests for the /poster/briefs endpoints.
# These test the HTTP layer — they mock the service layer.
#
# TESTS TO WRITE:
#
#   test_submit_brief_returns_201()
#       - POST /poster/briefs with valid payload + staff_token
#       - Assert: 201 Created, response contains brief_id and thread_id
#
#   test_submit_brief_requires_auth()
#       - POST /poster/briefs with NO Authorization header
#       - Assert: 401 Unauthorized
#
#   test_submit_brief_validates_platforms()
#       - POST with platforms=["myspace"]  (invalid)
#       - Assert: 422 Unprocessable Entity (Pydantic validation error)
#
#   test_get_brief_status()
#       - GET /poster/briefs/{id} with valid staff_token
#       - Assert: 200, returns correct status field
#
#   test_cannot_cancel_approved_brief()
#       - DELETE /poster/briefs/{id} where status="approved"
#       - Assert: 409 Conflict
# ─────────────────────────────────────────────────────────────────────────────
