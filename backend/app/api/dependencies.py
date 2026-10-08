from uuid import UUID

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer

from app.core.database import get_db
from app.core.security import TOKEN_TYPE_ACCESS, TokenError, decode_token
from app.models.user import User
from app.services.auth import get_user_by_id

from sqlalchemy.orm import Session

_oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")

_401 = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Not authenticated.",
    headers={"WWW-Authenticate": "Bearer"},
)


def get_current_user(
    token: str = Depends(_oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    try:
        payload = decode_token(token, expected_type=TOKEN_TYPE_ACCESS)
    except TokenError:
        raise _401

    try:
        user_id = UUID(payload["sub"])
    except (ValueError, KeyError):
        raise _401

    user = get_user_by_id(db, user_id)
    if user is None or not user.is_active:
        raise _401

    return user


# RBAC dependencies — no implicit hierarchy

def _require_roles(allowed: set[str]):
    """Factory returning a dependency that enforces an explicit role allowlist."""
    def dependency(current_user: User = Depends(get_current_user)) -> User:
        user_roles = {r.name for r in current_user.roles}
        if not user_roles & allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions.",
            )
        return current_user
    return dependency


require_employee = _require_roles({"EMPLOYEE"})
require_hr       = _require_roles({"HR", "ADMIN"})
require_admin    = _require_roles({"ADMIN"})
