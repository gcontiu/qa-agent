"""
JWT authentication for the FastAPI server.

Usage (in protected endpoints):
    from qa_agent.auth import CurrentUser, get_current_user
    from fastapi import Depends

    @app.get("/example")
    async def endpoint(user: CurrentUser = Depends(get_current_user)):
        ...  # user.user_id, user.email available

Local development (SUPABASE_URL not set):
    Returns a single dev user so the server works without Supabase configured.
    DATABASE_URL is also absent in that mode, so multi-tenancy is a no-op.

Supabase issues ES256 tokens (ECDSA P-256). The public key is fetched once from
the JWKS endpoint and cached in memory. No secret needed — only the public key.
"""
from __future__ import annotations

import json
import os
import uuid
from dataclasses import dataclass

import httpx
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt.algorithms import ECAlgorithm

_bearer = HTTPBearer(auto_error=False)

_DEV_USER_ID = "00000000-0000-0000-0000-000000000000"
_DEV_USER_EMAIL = "dev@localhost"

_cached_public_key = None


def _public_key():
    global _cached_public_key
    if _cached_public_key is not None:
        return _cached_public_key
    supabase_url = os.environ["SUPABASE_URL"].rstrip("/")
    resp = httpx.get(f"{supabase_url}/auth/v1/.well-known/jwks.json", timeout=10)
    resp.raise_for_status()
    first_key = resp.json()["keys"][0]
    _cached_public_key = ECAlgorithm.from_jwk(json.dumps(first_key))
    return _cached_public_key


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
      - ES256 signed with Supabase project's EC key (fetched once from JWKS)
      - aud = "authenticated" (set by Supabase for all user sessions)
      - sub present (user UUID)
      - not expired

    Raises HTTP 401 if any check fails.
    Falls back to dev user when SUPABASE_URL is unset.
    """
    if not os.getenv("SUPABASE_URL"):
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
            _public_key(),
            algorithms=["ES256"],
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

    try:
        uuid.UUID(user_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token sub claim is not a valid UUID",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return CurrentUser(user_id=user_id, email=payload.get("email", ""))
