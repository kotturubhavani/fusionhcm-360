"""Authentication service layer.

All functions operate at the domain level. No HTTPException is raised here.
HTTP status mapping is the responsibility of the API layer.
"""

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.core.config import settings
from app.core.security import (
    TOKEN_TYPE_REFRESH,
    TokenError,
    create_access_token,
    create_refresh_token,
    decode_token,
    dummy_verify,
    hash_password,
    verify_password,
)
from app.models.user import Role, User, UserRole
from app.schemas.auth import RegisterRequest


# ---------------------------------------------------------------------------
# Domain exceptions
# ---------------------------------------------------------------------------

class AuthServiceError(Exception):
    """Base class for auth service errors."""


class DuplicateEmailError(AuthServiceError):
    """A user with this email already exists."""


class InvalidCredentialsError(AuthServiceError):
    """Email/password combination is invalid."""


class InactiveUserError(AuthServiceError):
    """The user account is inactive."""


class RoleConfigurationError(AuthServiceError):
    """A required role is missing from the database."""


class InvalidRefreshTokenError(AuthServiceError):
    """The refresh token is missing, expired, or invalid."""


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _normalize_email(email: str) -> str:
    """Strip whitespace and lowercase for consistent storage and lookup."""
    return email.strip().lower()


def _get_role(db: Session, name: str) -> Role:
    role = db.execute(select(Role).where(Role.name == name)).scalar_one_or_none()
    if role is None:
        raise RoleConfigurationError(
            f"Required role '{name}' not found. Run seed_roles.py."
        )
    return role


# ---------------------------------------------------------------------------
# Public service functions
# ---------------------------------------------------------------------------

def register_user(db: Session, payload: RegisterRequest) -> User:
    """Register a new user and assign the EMPLOYEE role.

    Role assignment is not caller-controlled. Every registration receives
    exactly EMPLOYEE regardless of request content.
    """
    email = _normalize_email(str(payload.email))

    existing = db.execute(
        select(User).where(User.email == email)
    ).scalar_one_or_none()
    if existing is not None:
        raise DuplicateEmailError("An account with this email already exists.")

    employee_role = _get_role(db, "EMPLOYEE")

    user = User(
        email=email,
        password_hash=hash_password(payload.password),
        first_name=payload.first_name,
        last_name=payload.last_name,
    )
    db.add(user)

    try:
        db.flush()  # populate user.id; raises IntegrityError on constraint violation
        db.add(UserRole(user_id=user.id, role_id=employee_role.id))
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        # Use the structured constraint name from pg_constraint — no string parsing.
        constraint = getattr(exc.orig, "diag", None)
        constraint_name = (
            constraint.constraint_name
            if constraint is not None
            else ""
        )
        if constraint_name == "users_email_key":
            raise DuplicateEmailError("An account with this email already exists.") from None
        raise AuthServiceError("Registration failed due to a database error.") from None
    except Exception:
        db.rollback()
        raise AuthServiceError("Registration failed due to a database error.")

    # Reload explicitly with selectinload — do not rely on db.refresh() for roles.
    reloaded = get_user_by_id(db, user.id)
    if reloaded is None:
        raise AuthServiceError("User was created but could not be reloaded.")
    return reloaded


def authenticate_user(db: Session, email: str, password: str) -> User:
    """Verify credentials and return the authenticated User with roles loaded.

    Unknown email and wrong password produce the same exception to prevent
    user enumeration. Inactive accounts are rejected after credential check.
    """
    normalized = _normalize_email(email)

    user = db.execute(
        select(User)
        .where(User.email == normalized)
        .options(selectinload(User.roles))
    ).scalar_one_or_none()

    if user is None:
        dummy_verify(password)
        raise InvalidCredentialsError("Invalid email or password.")

    if not verify_password(password, user.password_hash):
        raise InvalidCredentialsError("Invalid email or password.")

    if not user.is_active:
        raise InactiveUserError("This account is inactive.")

    return user


def get_user_by_id(db: Session, user_id: UUID) -> User | None:
    """Load a user by UUID with roles eagerly loaded. Returns None if not found."""
    return db.execute(
        select(User)
        .where(User.id == user_id)
        .options(selectinload(User.roles))
    ).scalar_one_or_none()


# ---------------------------------------------------------------------------
# Token helpers
# ---------------------------------------------------------------------------

@dataclass
class TokenPair:
    access_token: str
    refresh_token: str
    expires_in: int  # access token lifetime in seconds


def issue_token_pair(user: User) -> TokenPair:
    """Derive current role names from the loaded user and issue both tokens.

    Does not persist tokens. No HTTP or cookie handling.
    """
    role_names = [r.name for r in user.roles]
    return TokenPair(
        access_token=create_access_token(subject=str(user.id), roles=role_names),
        refresh_token=create_refresh_token(subject=str(user.id)),
        expires_in=settings.access_token_expire_minutes * 60,
    )


def refresh_access_token(db: Session, refresh_token: str) -> tuple[str, int]:
    """Validate a refresh token string and issue a new access token.

    Accepts the raw refresh token string. Decoding and type validation happen
    here so the API layer only passes the cookie value through.

    Returns (new_access_token, expires_in_seconds).
    Refresh token rotation is not implemented at this stage.
    """
    try:
        payload = decode_token(refresh_token, expected_type=TOKEN_TYPE_REFRESH)
    except TokenError as exc:
        raise InvalidRefreshTokenError(str(exc)) from exc

    try:
        user_id = UUID(payload["sub"])
    except (ValueError, KeyError):
        raise InvalidRefreshTokenError("Refresh token subject is invalid.")

    user = get_user_by_id(db, user_id)
    if user is None:
        raise InvalidRefreshTokenError("User not found.")
    if not user.is_active:
        raise InactiveUserError("This account is inactive.")

    role_names = [r.name for r in user.roles]
    new_access_token = create_access_token(subject=str(user.id), roles=role_names)
    return new_access_token, settings.access_token_expire_minutes * 60
