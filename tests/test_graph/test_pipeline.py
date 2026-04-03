# tests/test_graph/test_pipeline.py
# ─────────────────────────────────────────────────────────────────────────────
# Integration tests for the full LangGraph pipeline (all agents mocked).
#
# TESTS TO WRITE:
#
#   test_pipeline_runs_all_5_agents_in_order()
#       - Mock all 5 agent functions
#       - Run graph from brief_parser to human_review pause point
#       - Assert call order: brief_parser → copywriter → designer → qa_agent
#
#   test_qa_low_confidence_regenerates_without_human()
#       - Mock qa_agent to return qa_confidence=0.40 on first call, 0.85 on second
#       - Assert: designer is called TWICE (once original, once after low QA)
#       - Assert: human_review is NOT reached until QA confidence >= 0.60
#
#   test_state_persists_across_interrupt()
#       - Use MemorySaver (in-memory checkpointer for tests, not PostgreSQL)
#       - Run to interrupt, then resume
#       - Assert: all state fields from before the interrupt are still intact after resume
#
# USE MemorySaver for tests, NOT PostgresSaver:
#   from langgraph.checkpoint.memory import MemorySaver
#   checkpointer = MemorySaver()
#   graph = build_graph_with_checkpointer(checkpointer)
# ─────────────────────────────────────────────────────────────────────────────
