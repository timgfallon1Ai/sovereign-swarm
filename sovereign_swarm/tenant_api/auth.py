"""JWT authentication for the Sovereign Tenant API.

Every tenant backend uses the same token schema:
    {
        "sub": "user@example.com",          # subject (user id)
        "tenant": "atx_mats",                # tenant key
        "exp": 1732920000,                   # expiry (unix timestamp)
        "iat": 1732833600,                   # issued at
        "scopes": ["crm.read", "crm.write"]  # optional
    }

Token generation is via `issue_token()`. Verification is via the
FastAPI dependency `require_tenant_claim(tenant_key)` which asserts
the JWT's `tenant` matches the expected value.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta
from typing import Any

from fastapi import Depends, Header, HTTPException, status
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------


def _secret() -> str:
    return os.getenv("JWT_SECRET", "dev-secret-change-me-in-production")


def _algorithm() -> str:
    return os.getenv("JWT_ALGORITHM", "HS256")


def _expires_hours() -> int:
    try:
        return int(os.getenv("JWT_EXPIRES_HOURS", "24"))
    except (ValueError, TypeError):
        return 24


_pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class TokenClaims(BaseModel):
    sub: str
    tenant: str
    exp: int
    iat: int
    scopes: list[str] = []


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


# ---------------------------------------------------------------------------
# Issuance + verification
# ---------------------------------------------------------------------------


def hash_password(plain: str) -> str:
    return _pwd.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return _pwd.verify(plain, hashed)
    except Exception:
        return False


def issue_token(
    subject: str,
    tenant: str,
    expires_hours: int | None = None,
    scopes: list[str] | None = None,
) -> str:
    """Issue an access token with tenant claim."""
    now = datetime.utcnow()
    exp = now + timedelta(hours=expires_hours or _expires_hours())
    payload: dict[str, Any] = {
        "sub": subject,
        "tenant": tenant,
        "iat": int(now.timestamp()),
        "exp": int(exp.timestamp()),
        "scopes": scopes or ["crm.read", "crm.write"],
    }
    return jwt.encode(payload, _secret(), algorithm=_algorithm())


def issue_refresh_token(subject: str, tenant: str) -> str:
    """Long-lived refresh token (30 days)."""
    now = datetime.utcnow()
    exp = now + timedelta(days=30)
    payload = {
        "sub": subject,
        "tenant": tenant,
        "typ": "refresh",
        "iat": int(now.timestamp()),
        "exp": int(exp.timestamp()),
    }
    return jwt.encode(payload, _secret(), algorithm=_algorithm())


def issue_token_pair(subject: str, tenant: str) -> TokenPair:
    return TokenPair(
        access_token=issue_token(subject, tenant),
        refresh_token=issue_refresh_token(subject, tenant),
        expires_in=_expires_hours() * 3600,
    )


def decode_token(token: str) -> TokenClaims:
    """Decode + validate a token. Raises HTTPException on invalid."""
    try:
        payload = jwt.decode(token, _secret(), algorithms=[_algorithm()])
    except JWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid token: {exc}",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
    try:
        return TokenClaims(**payload)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid token claims: {exc}",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc


# ---------------------------------------------------------------------------
# FastAPI dependencies
# ---------------------------------------------------------------------------


def require_tenant_claim(expected_tenant: str):
    """Factory returning a FastAPI dependency that asserts the token's
    `tenant` claim matches `expected_tenant`.
    """

    def dep(authorization: str = Header("")) -> TokenClaims:
        if not authorization or not authorization.lower().startswith("bearer "):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Missing bearer token",
                headers={"WWW-Authenticate": "Bearer"},
            )
        token = authorization[7:].strip()
        claims = decode_token(token)
        if claims.tenant != expected_tenant:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Token tenant mismatch: got {claims.tenant}, expected {expected_tenant}",
            )
        return claims

    return dep


def optional_tenant_claim(expected_tenant: str):
    """Lenient variant — returns claims if present, None otherwise.

    Used for endpoints that can be called without auth (e.g. login itself,
    inbound webhooks verified by a different mechanism).
    """

    def dep(authorization: str = Header("")) -> TokenClaims | None:
        if not authorization or not authorization.lower().startswith("bearer "):
            return None
        try:
            claims = decode_token(authorization[7:].strip())
            if claims.tenant != expected_tenant:
                return None
            return claims
        except HTTPException:
            return None

    return dep
