from typing import Any, Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, EmailStr, Field, field_validator


class RegisterRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: EmailStr
    password: str = Field(min_length=12, max_length=128)
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)

    @field_validator("first_name", "last_name", mode="before")
    @classmethod
    def strip_whitespace(cls, v: str) -> str:
        if isinstance(v, str):
            return v.strip()
        return v


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # Existing accounts may use local domains; registration still validates email.
    email: str = Field(strict=True, min_length=1, max_length=255)
    password: str = Field(max_length=128)


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: str = Field(strict=True, min_length=1, max_length=255)
    first_name: str
    last_name: str
    is_active: bool
    roles: list[str]
    created_at: AwareDatetime
    updated_at: AwareDatetime

    @field_validator("roles", mode="before")
    @classmethod
    def resolve_roles(cls, v: Any) -> list[str]:
        result = []
        for item in v:
            if isinstance(item, str):
                result.append(item)
            elif hasattr(item, "name"):
                result.append(item.name)
            else:
                raise ValueError(f"Cannot resolve role name from {type(item)}")
        return result


class TokenResponse(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int


class MessageResponse(BaseModel):
    message: str
