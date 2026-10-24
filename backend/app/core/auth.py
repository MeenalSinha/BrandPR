"""Authentication and cryptographically signed JWT token management for BrandPR.

Tokens use standard RFC 7519 HMAC-SHA256 signatures with constant-time verification.
Authorization decisions are made strictly from verified claims, never from client-asserted headers.
"""
import base64
import hashlib
import hmac
import json
import time
from typing import Any

from app.core.config import get_settings


DEMO_USERS = {
    "creator@brandpr.internal": {
        "id": "usr-creator-01",
        "name": "Morgan Lead",
        "email": "creator@brandpr.internal",
        "role": "creator",
        "password": "brandpr_creator_demo",
        "brand_ids": ["*"],
    },
    "reviewer@brandpr.internal": {
        "id": "usr-reviewer-01",
        "name": "Alex Compliance",
        "email": "reviewer@brandpr.internal",
        "role": "reviewer",
        "password": "brandpr_reviewer_demo",
        "brand_ids": ["*"],
    },
    "eve@external.internal": {
        "id": "usr-unauthorized-01",
        "name": "Eve Unauthorized",
        "email": "eve@external.internal",
        "role": "creator",
        "password": "brandpr_eve_demo",
        "brand_ids": ["00000000-0000-0000-0000-000000000000"],
    },
}


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def _b64url_decode(data: str) -> bytes:
    pad = len(data) % 4
    if pad:
        data += "=" * (4 - pad)
    return base64.urlsafe_b64decode(data.encode())


def create_access_token(payload: dict[str, Any], secret: str | None = None, expires_in: int = 86400 * 7) -> str:
    """Create an HMAC-SHA256 signed JWT string."""
    key = (secret or get_settings().jwt_secret).encode()
    header = {"alg": "HS256", "typ": "JWT"}
    now = int(time.time())
    claims = {**payload, "iat": now, "exp": now + expires_in}

    h_str = _b64url_encode(json.dumps(header, separators=(",", ":")).encode())
    p_str = _b64url_encode(json.dumps(claims, separators=(",", ":")).encode())
    signing_input = f"{h_str}.{p_str}".encode()
    signature = _b64url_encode(hmac.new(key, signing_input, hashlib.sha256).digest())
    return f"{h_str}.{p_str}.{signature}"


def decode_access_token(token: str, secret: str | None = None) -> dict[str, Any]:
    """Decode and cryptographically verify an HMAC-SHA256 signed JWT string."""
    parts = token.strip().split(".")
    if len(parts) != 3:
        raise ValueError("Invalid JWT format (expected 3 parts)")

    h_str, p_str, sig_str = parts
    key = (secret or get_settings().jwt_secret).encode()
    signing_input = f"{h_str}.{p_str}".encode()
    expected_sig = _b64url_encode(hmac.new(key, signing_input, hashlib.sha256).digest())

    if not hmac.compare_digest(sig_str, expected_sig):
        raise ValueError("Invalid cryptographic token signature")

    claims = json.loads(_b64url_decode(p_str).decode())
    if "exp" in claims and time.time() > claims["exp"]:
        raise ValueError("Authentication token has expired")

    return claims


def authenticate_user(email: str, password: str | None = None, demo_role: str | None = None) -> dict[str, Any] | None:
    """Validate user credentials or demo role."""
    if demo_role:
        for u in DEMO_USERS.values():
            if u["role"] == demo_role.lower():
                return u
        return None

    email_norm = email.strip().lower()
    user = DEMO_USERS.get(email_norm)
    if not user:
        return None
    if password is not None and user["password"] != password:
        return None
    return user
