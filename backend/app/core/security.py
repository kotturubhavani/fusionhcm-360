from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

import jwt
from pwdlib import PasswordHash
from pwdlib.hashers.argon2 import Argon2Hasher

from app.core.config import settings


# ---------------------------------------------------------------------------
# Password hashing
# ---------------------------------------------------------------------------

_password_hash = PasswordHash((Argon2Hasher(),))

# Precomputed Argon2 hash used to perform comparable password-hashing work
# when an email is not found, reducing timing differences. Generated once;
# the original plaintext is not needed or stored.
_DUMMY_HASH = (
    "$argon2id$v=19$m=65536,t=3,p=4"
    "$Xcz5aJ4V6Rt6mIv53rXyng$JWqkCh3MX3HaxjXgavjeD8K2c+9+01t7eK3RdTGKpmY"
)


def hash_password(password: str) -> str:
    return _password_hash.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return _password_hash.verify(password, password_hash)


def dummy_verify(password: str) -> None:
    """Perform a real Argon2 verification against a dummy hash.

    Call this when a login email is not found to reduce timing differences
    compared with a real failed verification.
    """
    _password_hash.verify(password, _DUMMY_HASH)


# ---------------------------------------------------------------------------
# JWT
# ---------------------------------------------------------------------------

TOKEN_TYPE_ACCESS = "access"
TOKEN_TYPE_REFRESH = "refresh"


class TokenError(Exception):
    """Raised when a JWT cannot be decoded or fails validation."""


def _build_payload(
    subject: str,
    token_type: str,
    expire_delta: timedelta,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    now = datetime.now(UTC)
    payload: dict[str, Any] = {
        "sub": subject,
        "type": token_type,
        "iat": now,
        "exp": now + expire_delta,
        "jti": str(uuid4()),
    }
    if extra:
        payload.update(extra)
    return payload


def create_access_token(subject: str, roles: list[str]) -> str:
    payload = _build_payload(
        subject=subject,
        token_type=TOKEN_TYPE_ACCESS,
        expire_delta=timedelta(minutes=settings.access_token_expire_minutes),
        extra={"roles": roles},
    )
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def create_refresh_token(subject: str) -> str:
    payload = _build_payload(
        subject=subject,
        token_type=TOKEN_TYPE_REFRESH,
        expire_delta=timedelta(days=settings.refresh_token_expire_days),
    )
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def decode_token(token: str, expected_type: str) -> dict[str, Any]:
    """Decode and validate a JWT.

    Raises TokenError for any validation failure so callers never
    handle raw PyJWT exceptions or see internal details.
    """
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
            options={"require": ["sub", "type", "iat", "exp", "jti"]},
        )
    except jwt.ExpiredSignatureError:
        raise TokenError("Token has expired")
    except jwt.InvalidTokenError:
        raise TokenError("Token is invalid")

    if payload.get("type") != expected_type:
        raise TokenError(f"Expected token type '{expected_type}'")

    return payload
