"""Directory configuration, and signing users in through it.

A directory user gets a local row on first sign-in (auth_source 'ldap'); at
every sign-in its name, e-mail and role are refreshed from the directory, so
removing someone from the mapped group takes effect at their next sign-in.
A local account with the same username always wins: the directory never takes
over an existing local user.

Every directory contact (sign-in, lookup, test) records whether the directory was
reachable. That record is written on its own short session so it survives the
caller's transaction rolling back (the dashboard warns while it is unreachable).
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from typing import Any

import structlog
from anyio import to_thread
from sqlalchemy.ext.asyncio import AsyncSession

from src.contracts.dto.directory.directory_config_dto import DirectoryConfigDTO
from src.contracts.dto.identity.user_dto import UserDTO
from src.core.context import Actor
from src.directory.ldap_client import (
    ConnectionFactory,
    DirectoryAuthFailed,
    DirectoryClient,
    DirectoryError,
    DirectorySettings,
    DirectoryUser,
    default_connection,
)
from src.errors.exceptions import ConflictError, DirectoryUnavailable, NotFoundError
from src.models import utcnow
from src.repositories.directory.directory_config_repository import DirectoryConfigRepository
from src.repositories.identity.user_repository import UserRepository
from src.services.audit.audit_service import AuditService
from src.services.vault.vault_service import VaultService

__all__ = ["DirectoryService", "default_connection", "set_connection_factory"]

logger = structlog.get_logger(__name__)

SideSessions = Callable[[], AbstractAsyncContextManager[AsyncSession]]

BIND_SECRET = "directory_bind"
# Never verifies: argon2 rejects it as a malformed hash.
NO_LOCAL_PASSWORD = "!directory"
# disabled_reason of users the directory sync disabled (and may re-enable).
SYNC_DISABLED = "directory_sync"

# The vault keys secrets by (owner_type, owner_id); the config is a singleton.
_CONFIG_OWNER = uuid.UUID(int=1)

_factory: ConnectionFactory = default_connection


def set_connection_factory(factory: ConnectionFactory) -> None:
    """Tests swap in ldap3's mock connections here."""
    global _factory
    _factory = factory


class DirectoryService:
    def __init__(
        self,
        config: DirectoryConfigRepository,
        users: UserRepository,
        vault: VaultService,
        audit: AuditService,
        side_sessions: SideSessions | None = None,
    ) -> None:
        self._config = config
        self._users = users
        self._vault = vault
        self._audit = audit
        self._side_sessions = side_sessions

    async def get_config(self) -> DirectoryConfigDTO | None:
        return await self._config.get()

    async def is_enabled(self) -> bool:
        cfg = await self.get_config()
        return bool(cfg and cfg.enabled)

    async def save_config(
        self, actor: Actor, values: dict[str, Any], bind_password: str | None
    ) -> DirectoryConfigDTO:
        current = await self._config.get(lock=True)
        changes = dict(values)
        bind_version = current.bind_secret_version if current else None
        if bind_password:
            bind_version = await self._vault.next_version(BIND_SECRET, _CONFIG_OWNER)
            await self._vault.store(
                owner_type=BIND_SECRET,
                owner_id=_CONFIG_OWNER,
                version=bind_version,
                plaintext=bind_password,
                created_by=actor.id,
            )
            changes["bind_secret_version"] = bind_version
        if changes["enabled"] and bind_version is None:
            raise ConflictError("Set the service-account password before enabling the directory")
        if changes.get("nested_groups") is None:
            # On by default for Active Directory; OpenLDAP has no in-chain matching rule.
            changes["nested_groups"] = changes.get("attr_username", "").lower() == "samaccountname"
        changes["updated_by"] = actor.id
        cfg = await self._config.save(changes)
        await self._audit.record(
            actor,
            "directory.configure",
            object_type="directory",
            details={
                "enabled": cfg.enabled,
                "server_url": cfg.server_url,
                "bind_dn": cfg.bind_dn,
                "bind_password_changed": bool(bind_password),
                "role_mappings": cfg.role_mappings,
                "default_role": cfg.default_role,
                "nested_groups": cfg.nested_groups,
            },
        )
        await self._config.commit()
        return cfg

    async def client(self) -> DirectoryClient:
        """A client for the configured directory, signed in as the service account."""
        cfg = await self.get_config()
        if cfg is None:
            raise NotFoundError("No directory is configured")
        return DirectoryClient(await self._settings(cfg), _factory)

    async def test_lookup(self, actor: Actor, username: str) -> DirectoryUser:
        """Service-account lookup of one user, without their password: shows DN, groups, role."""
        client = await self.client()
        try:
            user = await self._contact(client.lookup, username)
        except DirectoryAuthFailed as exc:
            raise NotFoundError(f"Lookup failed: {exc}") from exc
        finally:
            await self._audit.record(
                actor,
                "directory.test",
                object_type="directory",
                details={"username": username},
            )
            await self._config.commit()
        return user

    async def authenticate(self, username: str, password: str) -> DirectoryUser:
        """Raises DirectoryAuthFailed (bad credentials / no role) or DirectoryUnavailable."""
        client = await self.client()
        return await self._contact(client.authenticate, username, password)

    async def lookup(self, username: str) -> DirectoryUser:
        """Service-account lookup (groups refresh). DirectoryAuthFailed: no such user."""
        client = await self.client()
        return await self._contact(client.lookup, username)

    async def _contact(self, call: Callable[..., DirectoryUser], *args: str) -> DirectoryUser:
        """Run a directory call in a thread and record whether the directory answered."""
        try:
            result = await to_thread.run_sync(call, *args)
        except DirectoryError as exc:
            await self.record_reachability(False, str(exc))
            raise DirectoryUnavailable(str(exc)) from exc
        except DirectoryAuthFailed:
            await self.record_reachability(True)
            raise
        await self.record_reachability(True)
        return result

    async def record_reachability(self, ok: bool, error: str | None = None) -> None:
        if not ok:
            logger.warning("directory_unreachable", error=error)
        if self._side_sessions is None:
            return
        async with self._side_sessions() as session:
            repo = DirectoryConfigRepository(session)
            await repo.record_reachability(ok, error, utcnow())
            await repo.commit()

    async def recently_unreachable(self, retry_seconds: int) -> bool:
        """The last contact failed less than ``retry_seconds`` ago: don't try again yet."""
        cfg = await self.get_config()
        if cfg is None or cfg.reachable is not False or cfg.reachability_checked_at is None:
            return False
        return (utcnow() - cfg.reachability_checked_at).total_seconds() < retry_seconds

    async def upsert_user(self, existing: UserDTO | None, found: DirectoryUser) -> UserDTO:
        """Create or refresh the local row for a directory user (caller commits)."""
        profile = {
            "role": found.role,
            "email": found.email,
            "full_name": found.full_name,
            "external_id": found.dn,
            "directory_synced_at": utcnow(),
        }
        if existing is None:
            return await self._users.create(
                {
                    "username": found.username,
                    "password_hash": NO_LOCAL_PASSWORD,
                    "auth_source": "ldap",
                    **profile,
                }
            )
        changes: dict[str, Any] = {}
        if existing.role != found.role:
            # A role change ends existing sessions, like an admin edit would.
            changes["token_version"] = existing.token_version + 1
        if existing.disabled_reason == SYNC_DISABLED:
            # Disabled only because the directory had dropped them; it vouches for them again.
            changes["is_active"] = True
            changes["disabled_reason"] = None
        return await self._users.update(existing.id, {**changes, **profile})

    async def _settings(self, cfg: DirectoryConfigDTO) -> DirectorySettings:
        if cfg.bind_secret_version is None:
            raise DirectoryUnavailable("The directory has no service-account password set")
        password = await self._vault.read(
            owner_type=BIND_SECRET, owner_id=_CONFIG_OWNER, version=cfg.bind_secret_version
        )
        return DirectorySettings(
            server_url=cfg.server_url,
            bind_dn=cfg.bind_dn,
            bind_password=password,
            user_base_dn=cfg.user_base_dn,
            user_filter=cfg.user_filter,
            attr_username=cfg.attr_username,
            attr_email=cfg.attr_email,
            attr_full_name=cfg.attr_full_name,
            start_tls=cfg.start_tls,
            verify_tls=cfg.verify_tls,
            ca_cert_pem=cfg.ca_cert_pem,
            group_base_dn=cfg.group_base_dn,
            group_filter=cfg.group_filter,
            role_mappings=tuple((m["group_dn"], m["role"]) for m in cfg.role_mappings),
            default_role=cfg.default_role,
            timeout_seconds=cfg.timeout_seconds,
            nested_groups=cfg.nested_groups,
        )
