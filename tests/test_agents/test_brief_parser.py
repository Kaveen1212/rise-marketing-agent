# tests/test_agents/test_brief_parser.py
# ─────────────────────────────────────────────────────────────────────────────
# Unit tests for Agent 1 — Brief Parser Agent.
#
# TESTING STRATEGY:
#   Mock all LLM calls (langchain_anthropic.ChatAnthropic) using pytest-mock
#   or unittest.mock. We are testing the AGENT LOGIC, not Claude's intelligence.
#
# TESTS TO WRITE:
#
#   test_brief_parser_extracts_all_fields()
#       - Input: a raw PosterState with campaign_topic + other brief fields
#       - Mock the LLM to return a structured BriefSchema JSON
#       - Assert: state contains structured audience_segment, tone, key_message
#
#   test_brief_parser_validates_brand_guidelines()
#       - Mock LLM + mock validate_brand_guidelines tool
#       - Assert the tool is called with the brief context
#
#   test_brief_parser_handles_missing_field()
#       - Input: brief without a required field (e.g., no tone)
#       - Assert: raises ValueError or returns a sensible error state
#
# HOW TO MOCK LLM CALLS:
#   with patch("langchain_anthropic.ChatAnthropic.invoke") as mock_llm:
#       mock_llm.return_value = AIMessage(content='{"field": "value"}')
#       result = brief_parser_agent(state)
# ─────────────────────────────────────────────────────────────────────────────
