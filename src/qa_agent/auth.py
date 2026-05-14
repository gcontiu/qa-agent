"""
JWT authentication for the FastAPI server.

Usage (in protected endpoints):
    from qa_agent.auth import CurrentUser, get_current_user
    from fastapi import Depends

    @app.get("/example")
    async def endpoint(user: CurrentUser = Depends(get_current_user)):
        ...  # user.user_id, user.email available

Local development (SUPABASE_JWT_SECRET not set):
    Returns a single dev user so the server works without Supabase configured.
    DATABASE_URL is also absent in that mode, so multi-tenancy is a no-op.
"""
from __future__ import annotations

import os
from dataclasses import dataclass

import jwt  # pyjwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

_bearer = HTTPBearer(auto_error=False)

# Sentinel used when SUPABASE_JWT_SECRET is not set (local dev only).
_DEV_USER_ID = "00000000-0000-0000-0000-000000000000"
_DEV_USER_EMAIL = "dev@localhost"


@dataclass(frozen=True)
class CurrentUser:
    user_id: str   # == auth.users.id == public.users.id
    email: str


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> CurrentUser:
    """
    FastAPI dependency: decode + validate the Supabase JWT.

    Token requirements:
      - HS256 signed with SUPABASE_JWT_SECRET
      - aud = "authenticated" (set by Supabase for all user sessions)
      - sub present (user UUID)
      - not expired

    Raises HTTP 401 if any check fails.
    Falls back to dev user when SUPABASE_JWT_SECRET is unset.
    """
    secret = os.getenv("SUPABASE_JWT_SECRET")
    if not secret:
        return CurrentUser(user_id=_DEV_USER_ID, email=_DEV_USER_EMAIL)

    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Authorization header",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        payload = jwt.decode(
            credentials.credentials,
            secret,
            algorithms=["HS256"],
            audience="authenticated",
        )
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token expired",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except jwt.InvalidTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid token: {exc}",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_id: str | None = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token missing sub claim",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return CurrentUser(user_id=user_id, email=payload.get("email", ""))
