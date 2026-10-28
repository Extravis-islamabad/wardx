"""Serving credentials to application identities (docs/phase1/CREDENTIAL_PROVIDER.md §3–§8).

A fetch is not a check-out: no check-out row, no rotate-after-use trigger, no wait for an
exclusive check-out, no approval workflow. It always serves the account's current
version. In order:
1. the app's fetch rate limit (shared by every API worker): 429 ``rate_limited``;
2. the match: only accounts in active safes where the app holds ``fetch``, on active
   targets, of the requested kind. None: 404 ``credential_not_found`` (never says
   whether the account exists); several: 409 ``credential_ambiguous``;
3. the safe requires approval and does not allow app fetches: ``approval_required``;
4. the account's rotation needs attention, its last verify was untrustworthy, nothing is
   stored or the stored secret is (flagged) empty: ``credential_unavailable.*``.
Every fetch, served or refused, is audited as ``secret.app_fetch`` with the account's
safe_id once an account is matched, and never with a secret value.
"""

from __future__ import annotations

import hashlib
import uuid
from typing import Any

from src.contracts.dto.provider.app_dto import AppPrincipalDTO
from src.contracts.dto.provider.credential_dto import (
    FetchCandidateDTO,
    FetchedCredentialDTO,
    FetchQueryDTO,
)
from src.contracts.dto.rotation.rotation_dto import NEEDS_ATTENTION, VERIFY_UNTRUSTWORTHY
from src.core.context import Actor
from src.core.enums import Role, SecretType
from src.errors.exceptions import AppError
from src.models import utcnow
from src.repositories.provider.credential_repository import CredentialRepository
from src.services.audit.audit_service import AuditService
from src.services.inventory.account_service import ACCOUNT_SECRET, HIGH_RISK_EMPTY_PASSWORD
from src.services.inventory.snmp_secrets import is_snmp, read_snmp_document
from src.services.provider.app_service import APP_FETCH_ACTION
from src.services.provider.provider_errors import (
    ApprovalRequired,
    CredentialAmbiguous,
    CredentialNotFound,
    NoSecret,
    RateLimited,
    RotationNeedsAttention,
    VerifyUntrustworthy,
)
from src.services.provider.rate_limit_service import RateLimitService, fetch_bucket
from src.services.vault.vault_service import VaultService

# Credential kind -> the account secret types that serve it.
KIND_TYPES: dict[str, tuple[str, ...]] = {
    "ssh": (SecretType.PASSWORD.value, SecretType.SSH_KEY.value),
    "enable": (SecretType.ENABLE_SECRET.value,),
    "api": (SecretType.API_KEY.value,),
    "snmp": (SecretType.SNMP_V2C.value, SecretType.SNMP_V3.value),
}
TYPE_KIND = {t: kind for kind, types in KIND_TYPES.items() for t in types}
_NOT_FOUND = "No credential matches, or this application may not fetch it"


def version_id(account_id: uuid.UUID, secret_version: int) -> str:
    """Opaque and stable for one stored version; changes with every new version."""
    return "cv_" + hashlib.sha256(f"{account_id}:{secret_version}".encode()).hexdigest()[:32]


def shape_secret(secret_type: str, plaintext: str) -> dict[str, Any]:
    """The ``secret`` object by kind; empty when nothing usable is stored."""
    if is_snmp(secret_type):
        return read_snmp_document(plaintext)
    if not plaintext.strip():
        return {}
    field = {
        SecretType.SSH_KEY.value: "private_key",
        SecretType.API_KEY.value: "token",
    }.get(secret_type, "password")
    return {field: plaintext}


def _actor(app: AppPrincipalDTO) -> Actor:
    return Actor(id=app.id, username=f"app:{app.name}", role=Role.USER, source_ip=app.source_ip)


class CredentialService:
    def __init__(
        self,
        credentials: CredentialRepository,
        vault: VaultService,
        audit: AuditService,
        rate: RateLimitService,
    ) -> None:
        self._credentials = credentials
        self._vault = vault
        self._audit = audit
        self._rate = rate

    async def fetch(self, app: AppPrincipalDTO, query: FetchQueryDTO) -> FetchedCredentialDTO:
        base = {
            "kind": query.kind,
            "purpose": query.purpose,
            "match_by": query.match_by,
            "target_query": query.external_ref or query.address or query.name,
            "username": query.username,
        }
        await self._rate_limit(app, base)
        found = await self._credentials.find(app.id, query, KIND_TYPES[query.kind])
        if not found:
            await self._refuse(app, None, base, CredentialNotFound(_NOT_FOUND))
        if len(found) > 1:
            await self._refuse(
                app,
                None,
                {**base, "matches": len(found)},
                CredentialAmbiguous(
                    "Several accounts match: send the username", {"matches": len(found)}
                ),
            )
        return await self._serve(app, found[0], query.kind, base)

    async def fetch_account(
        self, app: AppPrincipalDTO, account_id: uuid.UUID, purpose: str
    ) -> FetchedCredentialDTO:
        base = {"purpose": purpose, "match_by": "account_id", "account_id": str(account_id)}
        await self._rate_limit(app, base)
        candidate = await self._credentials.by_account(app.id, account_id)
        if candidate is None:
            await self._refuse(app, None, base, CredentialNotFound(_NOT_FOUND))
        kind = TYPE_KIND.get(candidate.secret_type, "ssh")
        return await self._serve(app, candidate, kind, {**base, "kind": kind})

    async def _rate_limit(self, app: AppPrincipalDTO, base: dict[str, Any]) -> None:
        allowed, retry_after = await self._rate.hit(fetch_bucket(app.id), app.rate_limit_per_minute)
        if not allowed:
            await self._refuse(
                app, None, base, RateLimited("Fetch rate limit reached; back off", retry_after)
            )

    async def _serve(
        self, app: AppPrincipalDTO, c: FetchCandidateDTO, kind: str, base: dict[str, Any]
    ) -> FetchedCredentialDTO:
        if c.approval_required and not c.allow_app_fetch:
            await self._refuse(
                app,
                c,
                base,
                ApprovalRequired("This safe requires approval and does not allow app fetches"),
            )
        if c.rotation_status == NEEDS_ATTENTION or await self._credentials.rotation_needs_attention(
            c.account_id
        ):
            await self._refuse(
                app, c, base, RotationNeedsAttention("A rotation of this account needs attention")
            )
        if c.sync_status == VERIFY_UNTRUSTWORTHY:
            await self._refuse(
                app,
                c,
                base,
                VerifyUntrustworthy("WardX cannot vouch for this account's current password"),
            )
        if not c.secret_version or HIGH_RISK_EMPTY_PASSWORD in c.risk_flags:
            await self._refuse(app, c, base, NoSecret("No usable secret is stored"))
        try:
            plaintext = await self._vault.read(
                owner_type=ACCOUNT_SECRET, owner_id=c.account_id, version=c.secret_version
            )
        except AppError as exc:
            await self._refuse(app, c, base, exc)
        secret = shape_secret(c.secret_type, plaintext)
        if not secret:
            await self._refuse(app, c, base, NoSecret("No usable secret is stored"))
        vid = version_id(c.account_id, c.secret_version)
        await self._audit.record(
            _actor(app),
            APP_FETCH_ACTION,
            object_type="account",
            object_id=c.account_id,
            safe_id=c.safe_id,
            details={**self._details(app, c, base), "version_id": vid},
        )
        await self._credentials.commit()
        return FetchedCredentialDTO(
            candidate=c,
            kind=kind,
            secret=secret,
            version_id=vid,
            max_cache_seconds=c.app_cache_seconds,
            issued_at=utcnow(),
        )

    @staticmethod
    def _details(
        app: AppPrincipalDTO, c: FetchCandidateDTO | None, base: dict[str, Any]
    ) -> dict[str, Any]:
        details = {**base, "app_id": str(app.id), "app_name": app.name}
        if c is not None:
            details.update(
                account_id=str(c.account_id),
                target_id=str(c.target_id),
                safe_id=str(c.safe_id),
                username=c.username,
            )
        return details

    async def _refuse(
        self,
        app: AppPrincipalDTO,
        c: FetchCandidateDTO | None,
        base: dict[str, Any],
        error: AppError,
    ) -> None:
        """Audit a refused fetch (committed, so it survives the error), then raise."""
        await self._audit.record(
            _actor(app),
            APP_FETCH_ACTION,
            object_type="account" if c else "app",
            object_id=c.account_id if c else app.id,
            safe_id=c.safe_id if c else None,
            outcome="failure",
            details={**self._details(app, c, base), "error_code": error.code},
        )
        await self._credentials.commit()
        raise error
