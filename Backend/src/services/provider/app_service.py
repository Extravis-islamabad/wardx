"""Application identities: create, change, enable or disable, and their client secrets
(docs/phase1/CREDENTIAL_PROVIDER.md §1). Gated by ``apps.manage``.

Rules:
- An app is created with its first client secret, shown once. Only an argon2id hash
  and a short prefix are stored; the plaintext is never stored, logged or audited.
- At most two unrevoked secrets per app (slots 1 and 2, enforced by a unique index):
  add a second, move the collectors, revoke the first. An expired secret keeps its slot
  until it is revoked.
- Disabling an app bumps its token_version: every outstanding token dies at once.
- An empty IP allowlist means no access; the console warns.
- Every change is audited with before and after values (never a secret).
"""

from __future__ import annotations

import secrets
import uuid
from datetime import datetime
from typing import Any

from src.contracts.dto.audit.audit_event_dto import AuditEventDTO, AuditFilterDTO
from src.contracts.dto.provider.app_dto import AppDTO, NewAppSecretDTO
from src.core.client_ip import parse_networks
from src.core.context import Actor
from src.core.security import hash_password
from src.errors.exceptions import AppError, ConflictError, NotFoundError
from src.models import utcnow
from src.repositories.provider.app_repository import AppRepository
from src.services.audit.audit_service import AuditService

APP_FETCH_ACTION = "secret.app_fetch"
CLIENT_ID_PREFIX = "wxa_"
CLIENT_SECRET_PREFIX = "wxs_"
_PREFIX_CHARS = 12
MAX_ACTIVE_SECRETS = 2


class InvalidAppSettings(AppError):
    status_code = 422
    code = "validation_error"


def normalise_allowlist(cidrs: list[str]) -> list[str]:
    """Each entry as a network in canonical form (a bare address becomes a /32 or /128)."""
    try:
        networks = parse_networks(cidrs)
    except ValueError as exc:
        raise InvalidAppSettings(f"Not a valid IP address or CIDR: {exc}") from exc
    return sorted({str(n) for n in networks})


def new_client_secret() -> str:
    return CLIENT_SECRET_PREFIX + secrets.token_urlsafe(32)


class AppService:
    def __init__(self, apps: AppRepository, audit: AuditService) -> None:
        self._apps = apps
        self._audit = audit

    async def list(
        self, *, search: str | None, page: int, page_size: int
    ) -> tuple[list[AppDTO], int]:
        return await self._apps.list(search=search, page=page, page_size=page_size)

    async def get(self, app_id: uuid.UUID, *, lock: bool = False) -> AppDTO:
        app = await self._apps.get(app_id, lock=lock)
        if app is None:
            raise NotFoundError("Application identity not found")
        return app

    async def create(
        self, actor: Actor, values: dict[str, Any], secret_expires_at: datetime | None
    ) -> NewAppSecretDTO:
        values = {
            **values,
            "ip_allowlist": normalise_allowlist(values.get("ip_allowlist") or []),
            "client_id": CLIENT_ID_PREFIX + secrets.token_hex(12),
            "created_by": actor.id,
        }
        app_id = await self._apps.create(values)
        app = await self.get(app_id)
        await self._audit.record(
            actor,
            "app.create",
            object_type="app",
            object_id=app_id,
            details={"client_id": app.client_id, "after": app.audit_view()},
        )
        return await self._add_secret(actor, app, secret_expires_at)

    async def update(self, actor: Actor, app_id: uuid.UUID, changes: dict[str, Any]) -> AppDTO:
        before = await self.get(app_id, lock=True)
        if "ip_allowlist" in changes:
            changes["ip_allowlist"] = normalise_allowlist(changes["ip_allowlist"] or [])
        await self._apps.update(app_id, changes)
        if before.enabled and changes.get("enabled") is False:
            await self._apps.bump_token_version(app_id)
        after = await self.get(app_id)
        action = "app.update"
        if before.enabled != after.enabled:
            action = "app.enable" if after.enabled else "app.disable"
        await self._audit.record(
            actor,
            action,
            object_type="app",
            object_id=app_id,
            details={"before": before.audit_view(), "after": after.audit_view()},
        )
        await self._apps.commit()
        return after

    async def add_secret(
        self, actor: Actor, app_id: uuid.UUID, expires_at: datetime | None
    ) -> NewAppSecretDTO:
        return await self._add_secret(actor, await self.get(app_id, lock=True), expires_at)

    async def _add_secret(
        self, actor: Actor, app: AppDTO, expires_at: datetime | None
    ) -> NewAppSecretDTO:
        if expires_at is not None and expires_at <= utcnow():
            raise InvalidAppSettings("A secret's expiry must be in the future")
        used = {s.slot for s in app.secrets if s.revoked_at is None}
        free = [slot for slot in (1, 2) if slot not in used]
        if not free:
            raise ConflictError(
                "This application identity already has two active secrets; revoke one first"
            )
        plaintext = new_client_secret()
        secret = await self._apps.add_secret(
            {
                "app_id": app.id,
                "slot": free[0],
                "secret_hash": await hash_password(plaintext),
                "prefix": plaintext[:_PREFIX_CHARS],
                "expires_at": expires_at,
                "created_by": actor.id,
            }
        )
        await self._audit.record(
            actor,
            "app.secret_add",
            object_type="app",
            object_id=app.id,
            details={
                "secret_id": str(secret.id),
                "prefix": secret.prefix,
                "expires_at": expires_at.isoformat() if expires_at else None,
            },
        )
        await self._apps.commit()
        return NewAppSecretDTO(app=await self.get(app.id), secret=secret, client_secret=plaintext)

    async def revoke_secret(self, actor: Actor, app_id: uuid.UUID, secret_id: uuid.UUID) -> AppDTO:
        await self.get(app_id, lock=True)
        secret = await self._apps.get_secret(secret_id)
        if secret is None or secret.app_id != app_id:
            raise NotFoundError("Secret not found")
        if secret.revoked_at is not None:
            raise ConflictError("This secret is already revoked")
        await self._apps.revoke_secret(secret_id, utcnow())
        await self._audit.record(
            actor,
            "app.secret_revoke",
            object_type="app",
            object_id=app_id,
            details={"secret_id": str(secret_id), "prefix": secret.prefix},
        )
        await self._apps.commit()
        return await self.get(app_id)

    async def recent_fetches(
        self, app_id: uuid.UUID, *, page: int, page_size: int
    ) -> tuple[list[AuditEventDTO], int]:
        await self.get(app_id)
        return await self._audit.list_events(
            AuditFilterDTO(action=APP_FETCH_ACTION, actor_id=app_id), page=page, page_size=page_size
        )
