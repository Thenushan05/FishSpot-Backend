"""Authentication dependencies for FastAPI routes.

This module extracts JWT from either the Authorization header or an
`access_token` httpOnly cookie (dev convenience). It decodes and returns a
minimal user context. In production you may prefer to only accept Authorization
headers and/or use session cookies with CSRF protection.
"""
from typing import Optional

from fastapi import Request, HTTPException, status

from app.core.security import decode_access_token


def get_token_from_request(request: Request) -> Optional[str]:
    auth = request.headers.get("Authorization")
    if auth and auth.lower().startswith("bearer "):
        return auth.split(" ", 1)[1]

    # Fallback to cookie named `access_token`
    token = request.cookies.get("access_token")
    if token:
        return token

    return None


def get_current_user(request: Request) -> dict:
    token = get_token_from_request(request)
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing auth token")

    try:
        payload = decode_access_token(token)
    except Exception:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid auth token")

    if not payload or "sub" not in payload:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload")

    # MongoDB uses string ObjectIDs, SQLite uses integers
    user_id = payload.get("sub")
    # Keep as string for MongoDB compatibility
    return {"user_id": str(user_id), "raw": payload}
