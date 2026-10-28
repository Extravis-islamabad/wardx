"""Credential provider request shapes (docs/phase1/CREDENTIAL_PROVIDER.md §2, §4)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator

CredentialKind = Literal["ssh", "snmp", "api", "enable"]
FetchPurpose = Literal["poll", "ncm_backup", "onboarding", "other"]


class TokenRequest(BaseModel):
    client_id: str = Field(min_length=1, max_length=64)
    client_secret: str = Field(min_length=1, max_length=256)


class FetchTarget(BaseModel):
    """Exactly one of external_ref (MonetX's device id, preferred), address or name."""

    external_ref: str | None = Field(None, min_length=1, max_length=255)
    address: str | None = Field(None, min_length=1, max_length=255)
    name: str | None = Field(None, min_length=1, max_length=255)

    @model_validator(mode="after")
    def _exactly_one(self) -> FetchTarget:
        given = [v for v in (self.external_ref, self.address, self.name) if v is not None]
        if len(given) != 1:
            raise ValueError("Give exactly one of external_ref, address or name")
        return self


class CredentialFetch(BaseModel):
    target: FetchTarget
    kind: CredentialKind
    # Required when the app may fetch several accounts of this kind on the target.
    username: str | None = Field(None, min_length=1, max_length=255)
    purpose: FetchPurpose


class AccountFetch(BaseModel):
    purpose: FetchPurpose
