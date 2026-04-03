"""
app/api/deps.py
─────────────────────────────────────────────────────────────────────────────
FastAPI dependencies — injected into every route via Depends().

FastAPI calls these functions automatically before each route handler runs.
If a dependency raises HTTPException, the route never executes.

How to use in a route:
    from app.api.deps import get_db, require_reviewer

    @router.post("/approve")
    async def approve(
        db:   AsyncSession = Depends(get_db),
        user: UserPayload  = Depends(require_reviewer),
    ):
        ...  # db and user are ready to use here
─────────────────────────────────────────────────────────────────────────────
"""

from collections.abc import AsyncGenerator

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import UserPayload, require_role, require_reviewer, require_staff
from app.database import get_session


# ─────────────────────────────────────────────────────────────────────────────
# Database session dependency
# ─────────────────────────────────────────────────────────────────────────────

async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    Provides a request-scoped async SQLAlchemy session.

    This is a thin wrapper around database.get_session() so route files
    import from one consistent place (app.api.deps) instead of mixing
    imports from app.database and app.api.deps.

    The session commits on success and rolls back on exception.
    Always closed in the finally block — no connection leaks.
    """
    async for session in get_session():
        yield session


# ─────────────────────────────────────────────────────────────────────────────
# Auth dependencies — re-exported from security.py for clean imports
# ─────────────────────────────────────────────────────────────────────────────

# Use these directly in route Depends() calls:
#
#   Depends(require_staff)    → staff, marketing, reviewer, admin
#   Depends(require_reviewer) → reviewer, admin only (HITL gate)

# Re-export so routes only need: from app.api.deps import get_db, require_reviewer
__all__ = [
    "get_db",
    "require_staff",
    "require_reviewer",
    "UserPayload",
]
