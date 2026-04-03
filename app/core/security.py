"""
app/core/security.py
─────────────────────────────────────────────────────────────────────────────
JWT validation and role-based access control.

How auth works in this system:
  1. The frontend (Next.js review UI) signs in via Supabase Auth
  2. Supabase returns a JWT signed with HS256 using API_SECRET_KEY
  3. Frontend sends: Authorization: Bearer <token> on every API request
  4. This module verifies the token and extracts the user payload
  5. Roles are stored inside the JWT under app_metadata.role

Roles (from spec §5.1):
  "staff"      → can submit briefs
  "marketing"  → can submit briefs
  "reviewer"   → can submit briefs + review/approve/reject
  "admin"      → full access to everything
─────────────────────────────────────────────────────────────────────────────
"""

from dataclasses import dataclass
from uuid import UUID

from fastapi import HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import ExpiredSignatureError, JWTError, jwt

from app.config import settings

# OAuth2PasswordBearer tells FastAPI where to find the token.
# tokenUrl is not used for login here (Supabase handles that) but FastAPI
# requires the field. The actual token comes from Authorization: Bearer <token>.
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/token", auto_error=True)


# ─────────────────────────────────────────────────────────────────────────────
# UserPayload — what we know about the authenticated user
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class UserPayload:
    """
    Decoded JWT payload — everything we need to know about the caller.

    user_id: UUID of the authenticated user (JWT "sub" claim)
    role:    Permission level from JWT app_metadata.role
    email:   User email — stored in the review audit log
    """
    user_id: UUID
    role: str
    email: str


# ─────────────────────────────────────────────────────────────────────────────
# decode_jwt
# ─────────────────────────────────────────────────────────────────────────────

def decode_jwt(token: str) -> UserPayload:
    """
    Verify and decode a JWT token.

    Uses python-jose to verify the HS256 signature against API_SECRET_KEY.
    Raises HTTP 401 if the token is expired or has an invalid signature.
    Raises HTTP 401 if required claims are missing.

    The JWT payload structure expected:
    {
      "sub": "uuid-of-user",
      "email": "reviewer@risetechvillage.lk",
      "app_metadata": { "role": "reviewer" },
      "exp": 1234567890
    }
    """
    credentials_error = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired token",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        payload = jwt.decode(
            token,
            settings.API_SECRET_KEY.get_secret_value(),
            algorithms=["HS256"],
        )
    except ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired — please sign in again",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except JWTError:
        raise credentials_error

    # Extract required claims
    sub: str | None = payload.get("sub")
    email: str | None = payload.get("email", "")

    if not sub:
        raise credentials_error

    # Role comes from app_metadata.role (Supabase convention)
    # Falls back to "staff" if not set — minimum permission level
    app_metadata: dict = payload.get("app_metadata", {})
    role: str = app_metadata.get("role", "staff")

    try:
        user_id = UUID(sub)
    except ValueError:
        raise credentials_error

    return UserPayload(user_id=user_id, role=role, email=email)


# ─────────────────────────────────────────────────────────────────────────────
# require_role — factory that returns a FastAPI dependency
# ─────────────────────────────────────────────────────────────────────────────

def require_role(*allowed_roles: str):
    """
    Returns a FastAPI dependency that:
      1. Extracts the Bearer token from Authorization header
      2. Decodes and verifies it
      3. Checks the user's role is in allowed_roles
      4. Returns the UserPayload if authorised
      5. Raises 403 Forbidden if the role is not permitted

    Usage in routes:
        @router.post("/approve")
        async def approve(user: UserPayload = Depends(require_role("reviewer", "admin"))):
            ...

    Args:
        *allowed_roles: One or more role strings that can access the route
    """
    # admin always has access regardless of which roles are listed
    effective_roles = set(allowed_roles) | {"admin"}

    async def _dependency(token: str = oauth2_scheme) -> UserPayload:  # type: ignore[return]
        user = decode_jwt(token)
        if user.role not in effective_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    f"Access denied. Required role: {list(allowed_roles)}. "
                    f"Your role: {user.role}"
                ),
            )
        return user

    return _dependency


# ─────────────────────────────────────────────────────────────────────────────
# Pre-built dependency instances — import these in route files
# ─────────────────────────────────────────────────────────────────────────────

# Any authenticated user — just needs a valid token
require_any_user = require_role("staff", "marketing", "reviewer", "admin")

# Can submit briefs
require_staff = require_role("staff", "marketing", "reviewer", "admin")

# Can approve / revise / reject posters — the HITL gate role check
require_reviewer = require_role("reviewer", "admin")
