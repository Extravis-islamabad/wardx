"""Host-key request shapes."""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator

from src.transport.routeros_api import normalise_fingerprint


class HostKeyAccept(BaseModel):
    # The fingerprint the administrator compared with the device (SHA256:...). The key is
    # pinned only if the device still presents exactly this one.
    fingerprint: str = Field(min_length=8, max_length=128, pattern=r"^SHA256:[A-Za-z0-9+/=]+$")


class TlsCertAccept(BaseModel):
    # The SHA-256 fingerprint of the certificate (DER) the administrator compared with the
    # device: 64 hex digits, with or without colons (RouterOS prints them without). The
    # certificate is pinned only if the device still presents exactly this one.
    fingerprint: str = Field(min_length=64, max_length=128)

    @field_validator("fingerprint")
    @classmethod
    def _sha256(cls, value: str) -> str:
        normalised = normalise_fingerprint(value)
        if normalised is None:
            raise ValueError("a SHA-256 fingerprint is 64 hex digits (colons optional)")
        return normalised
