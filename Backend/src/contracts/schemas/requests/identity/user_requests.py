"""User administration request shapes, and the password strength rule."""

from __future__ import annotations

from pydantic import BaseModel, EmailStr, Field, field_validator

from src.core.enums import Role

PASSWORD_MIN = 12


def check_password_strength(value: str) -> str:
    if len(value) < PASSWORD_MIN:
        raise ValueError(f"must be at least {PASSWORD_MIN} characters")
    classes = sum(
        [
            any(c.islower() for c in value),
            any(c.isupper() for c in value),
            any(c.isdigit() for c in value),
            any(not c.isalnum() for c in value),
        ]
    )
    if classes < 3:
        raise ValueError("must mix at least three of: lower case, upper case, digits, symbols")
    return value


class UserCreate(BaseModel):
    username: str = Field(min_length=3, max_length=150, pattern=r"^[A-Za-z0-9._@-]+$")
    password: str = Field(max_length=1024)
    email: EmailStr | None = None
    full_name: str | None = Field(None, max_length=255)
    role: Role = Role.USER

    _strength = field_validator("password")(check_password_strength)


class UserUpdate(BaseModel):
    email: EmailStr | None = None
    full_name: str | None = Field(None, max_length=255)
    role: Role | None = None
    is_active: bool | None = None


class PasswordReset(BaseModel):
    new_password: str = Field(max_length=1024)

    _strength = field_validator("new_password")(check_password_strength)
