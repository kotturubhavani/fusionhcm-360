from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

import jwt
from pwdlib import PasswordHash
from pwdlib.hashers.argon2 import Argon2Hasher

from app.core.config import settings


_password_hash = PasswordHash((Argon2Hasher(),))

# Unknown accounts perform the same Argon2 work as failed password checks.
_DUMMY_HASH = (
    "$argon2id$v=19$m=65536,t=3,p=4"
    "$Xcz5aJ4V6Rt6mIv53rXyng$JWqkCh3MX3HaxjXgavjeD8K2c+9+01t7eK3RdTGKpmY"
)


def hash_password(password: str) -> str:
    return _password_hash.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return _password_hash.verify(password, password_hash)


def dummy_verify(password: str) -> None:
    """Reduce login timing differences for unknown accounts."""
    _password_hash.verify(password, _DUMMY_HASH)


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
    """Validate a JWT and expose only TokenError on failure."""
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
