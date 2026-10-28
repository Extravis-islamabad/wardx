"""Safe and safe-member request shapes."""

from __future__ import annotations

from pydantic import BaseModel, Field

from src.core.enums import PrincipalType, SafePermission


class SafeCreate(BaseModel):
    name: str = Field(min_length=1, max_length=150)
    description: str | None = Field(None, max_length=2000)
    is_active: bool = True


class SafeUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=150)
    description: str | None = Field(None, max_length=2000)
    is_active: bool | None = None


class SafeMemberCreate(BaseModel):
    # user: the user's id; group: the directory group's DN; role: a WardX role
    # (kept for the Default safe's migrated members; the console offers users and groups).
    principal_type: PrincipalType
    principal_key: str = Field(min_length=1, max_length=1000)
    permissions: list[SafePermission] = Field(min_length=1, max_length=7)


class SafeMemberUpdate(BaseModel):
    permissions: list[SafePermission] = Field(min_length=1, max_length=7)
