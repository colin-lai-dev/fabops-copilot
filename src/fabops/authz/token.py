"""Short-lived identity tokens for the MCP boundary (ADR-0001, option A).

The API (or the eval runner, standing in for it) signs a token for the logged-in demo user;
the agent's MCP client sends it as `Authorization: Bearer …`; the MCP server verifies it and
resolves the user's scope from the `users` table. The token carries only the user id: the
scope is looked up server-side on every request, so a token cannot claim extra permissions.

Tokens live in memory and HTTP headers only; they are never written to traces or logs.
"""

from __future__ import annotations

import time

import jwt

ISSUER = "fabops-api"
AUDIENCE = "fabops-mcp"
ALGORITHM = "HS256"
DEFAULT_TTL_S = 300
MIN_SECRET_LEN = 32


def _check_secret(secret: str) -> None:
    if not secret or len(secret) < MIN_SECRET_LEN:
        raise ValueError(f"FABOPS_JWT_SECRET must be at least {MIN_SECRET_LEN} characters")


def issue_token(user_id: str, secret: str, ttl_s: int = DEFAULT_TTL_S) -> str:
    _check_secret(secret)
    now = int(time.time())
    claims = {"sub": user_id, "iss": ISSUER, "aud": AUDIENCE, "iat": now, "exp": now + ttl_s}
    return jwt.encode(claims, secret, algorithm=ALGORITHM)


def verify_token(token: str, secret: str) -> str:
    """Return the user id of a valid token; raise `jwt.InvalidTokenError` otherwise."""
    _check_secret(secret)
    claims = jwt.decode(
        token,
        secret,
        algorithms=[ALGORITHM],
        audience=AUDIENCE,
        issuer=ISSUER,
        options={"require": ["sub", "exp", "iss", "aud"]},
    )
    return str(claims["sub"])
