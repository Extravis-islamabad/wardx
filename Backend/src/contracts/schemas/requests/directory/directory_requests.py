"""Directory (LDAP / Active Directory) configuration and sync request shapes."""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator

from src.core.enums import Role

AD_USER_FILTER = "(&(objectClass=user)(sAMAccountName={username}))"


class RoleMapping(BaseModel):
    group_dn: str = Field(min_length=3, max_length=1000)
    role: Role


class DirectoryConfigIn(BaseModel):
    enabled: bool = False
    server_url: str = Field(pattern=r"^ldaps?://[^\s]+$", max_length=500)
    start_tls: bool = False
    verify_tls: bool = True
    ca_cert_pem: str | None = Field(None, max_length=20000)
    bind_dn: str = Field(min_length=3, max_length=1000)
    # Write-only: omitted or empty keeps the stored password.
    bind_password: str | None = Field(None, max_length=1024)
    user_base_dn: str = Field(min_length=3, max_length=1000)
    user_filter: str = Field(AD_USER_FILTER, max_length=1000)
    attr_username: str = Field("sAMAccountName", max_length=64)
    attr_email: str = Field("mail", max_length=64)
    attr_full_name: str = Field("displayName", max_length=64)
    group_base_dn: str | None = Field(None, max_length=1000)
    group_filter: str | None = Field(None, max_length=1000)
    role_mappings: list[RoleMapping] = Field(default_factory=list, max_length=100)
    default_role: Role | None = None
    timeout_seconds: int = Field(10, ge=1, le=60)
    # 0 = no scheduled sync; otherwise every 5-1440 minutes.
    sync_interval_minutes: int = Field(60, ge=0, le=1440)
    sync_max_disable_percent: int = Field(20, ge=1, le=100)

    @field_validator("sync_interval_minutes")
    @classmethod
    def _interval(cls, v: int) -> int:
        if 0 < v < 5:
            raise ValueError("use 0 (off) or at least 5 minutes")
        return v

    @field_validator("user_filter")
    @classmethod
    def _has_username(cls, v: str) -> str:
        if "{username}" not in v:
            raise ValueError("must contain {username}")
        return v

    @field_validator("group_filter")
    @classmethod
    def _has_user_dn(cls, v: str | None) -> str | None:
        if v and "{user_dn}" not in v:
            raise ValueError("must contain {user_dn}")
        return v


class DirectoryTest(BaseModel):
    username: str = Field(min_length=1, max_length=255)


class SyncRequest(BaseModel):
    dry_run: bool = False
    # Apply even past the disable limit, after an admin has reviewed the preview.
    force: bool = False
