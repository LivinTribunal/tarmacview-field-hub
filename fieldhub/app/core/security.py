"""x-auth-token jwt issue/verify and the backend-facing shared-secret gate."""

import secrets
from datetime import UTC, datetime, timedelta

from fastapi import Header, HTTPException
from jose import JWTError, jwt

from app.core.config import settings
from app.core.exceptions import HubApiError

CODE_UNAUTHORIZED = 401


def create_access_token(username: str) -> str:
    """issue a signed jwt for the manage api."""
    now = datetime.now(UTC)
    claims = {
        "sub": username,
        "user_id": settings.pilot_user_id,
        "workspace_id": settings.workspace_id,
        "iat": now,
        "exp": now + timedelta(minutes=settings.token_expiration_minutes),
    }
    return jwt.encode(claims, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def verify_token(token: str) -> dict:
    """decode and validate a jwt, returning its claims."""
    try:
        return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except JWTError:
        raise HubApiError(
            code=CODE_UNAUTHORIZED, message="invalid or expired token", http_status=401
        )


def require_pilot_token(x_auth_token: str | None = Header(default=None)) -> dict:
    """dependency: validate the x-auth-token header, return claims."""
    if not x_auth_token:
        raise HubApiError(code=CODE_UNAUTHORIZED, message="missing x-auth-token", http_status=401)
    return verify_token(x_auth_token)


def constant_time_equals(value: str, expected: str) -> bool:
    """timing-safe string comparison, safe for non-ascii input."""
    return secrets.compare_digest(value.encode(), expected.encode())


def require_hub_secret(x_hub_secret: str | None = Header(default=None)) -> None:
    """dependency: gate internal endpoints on the backend shared secret."""
    if not settings.shared_secret:
        raise HTTPException(status_code=503, detail="shared secret not configured")
    if not x_hub_secret or not constant_time_equals(x_hub_secret, settings.shared_secret):
        raise HTTPException(status_code=403, detail="invalid hub secret")
