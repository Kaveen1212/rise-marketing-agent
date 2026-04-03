# tests/conftest.py
# ─────────────────────────────────────────────────────────────────────────────
# pytest fixtures shared across all test modules.
#
# WHAT TO BUILD:
#
#   @pytest.fixture
#   def app() -> FastAPI
#       - Create the FastAPI test application
#       - Override get_db dependency with a test database session
#
#   @pytest.fixture
#   async def client(app) -> AsyncClient
#       - httpx AsyncClient pointing at the test app
#       - Used like: await client.post("/poster/briefs", json={...})
#
#   @pytest.fixture
#   def staff_token() -> str
#       - A fake JWT token with role="staff" for testing brief submission
#
#   @pytest.fixture
#   def reviewer_token() -> str
#       - A fake JWT token with role="reviewer" for testing review endpoints
#
#   @pytest.fixture
#   def sample_brief() -> dict
#       - A valid BriefCreate payload for reuse across tests
#
# HOW PYTEST FIXTURES WORK:
#   Fixtures are dependency-injected into test functions by name.
#   def test_something(client, sample_brief): ...
#   pytest finds "client" and "sample_brief" fixtures and runs them first.
# ─────────────────────────────────────────────────────────────────────────────
