# tests/test_graph/test_hitl_gate.py
# ─────────────────────────────────────────────────────────────────────────────
# THE MOST IMPORTANT TEST FILE IN THE PROJECT.
# Spec §7.3 Stage 2: "Verify interrupt() fires, approve/revise/reject paths all work"
#
# These tests prove the HITL gate is real — not a UI trick or a DB flag.
#
# TESTS TO WRITE:
#
#   test_graph_pauses_before_human_review()
#       - Run the full pipeline with all agents mocked
#       - Assert: graph.get_state(config).next == ("human_review",)
#       - This proves execution stopped BEFORE human_review, not after
#       - Assert: publisher_agent was NEVER called
#
#   test_approve_resumes_to_publisher()
#       - Set up graph paused at human_review
#       - Resume with Command(resume={"review_status": "approved", "review_scores": {...}})
#       - Assert: publisher_agent IS called
#       - Assert: poster_briefs.status == "approved"
#
#   test_revise_routes_back_to_designer()
#       - Resume with Command(resume={"review_status": "revision", "review_feedback": "fix colours"})
#       - Assert: designer_agent IS called again (revision cycle 1)
#       - Assert: revision_count == 1 in state
#
#   test_reject_routes_to_end()
#       - Resume with Command(resume={"review_status": "rejected"})
#       - Assert: publisher_agent is NEVER called
#       - Assert: graph terminates at END
#
#   test_publisher_cannot_run_without_approval()
#       - Try to call publisher_agent directly without going through graph
#       - Assert: it fails / state.review_status != "approved" prevents it
#       - This test proves the gate is architectural, not just a UI check
#
#   test_max_revision_cycles_enforced()
#       - Simulate 3 revision cycles (revision_count = 3)
#       - Assert: 4th revise request returns 409 Conflict
#       - Assert: poster_briefs.status == "exhausted"
# ─────────────────────────────────────────────────────────────────────────────
