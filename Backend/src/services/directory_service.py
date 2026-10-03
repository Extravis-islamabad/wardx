"""Directory configuration, and signing users in through it.

A directory user gets a local row on first sign-in (auth_source 'ldap'); at
every sign-in its name, e-mail and role are refreshed from the directory, so
removing someone from the mapped group takes effect at their next sign-in.
A local account with the same username always wins: the directory never takes
over an existing local user.
"""

from __future__ import annotations

import uuid
from typing import Any

from anyio import to_thread
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

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
from src.errors.exceptions import AppError, ConflictError, NotFoundError
from src.models import DirectoryConfig, Secret, User, utcnow
from src.services import audit_service, vault_service

BIND_SECRET = "directory_bind"
# Never verifies: argon2 rejects it as a malformed hash.
NO_LOCAL_PASSWORD = "!directory"

# The vault keys secrets by (owner_type, owner_id); the config is a singleton.
_CONFIG_OWNER = uuid.UUID(int=1)

_factory: ConnectionFactory = default_connection


def set_connection_factory(factory: ConnectionFactory) -> None:
    """Tests swap in ldap3's mock connections here."""
    global _factory
    _factory = factory


class DirectoryUnavailable(AppError):
    status_code = 502
    code = "directory_unavailable"


async def get_config(session: AsyncSession) -> DirectoryConfig | None:
    return await session.get(DirectoryConfig, 1)


async def _settings(session: AsyncSession, cfg: DirectoryConfig) -> DirectorySettings:
    if cfg.bind_secret_version is None:
        raise DirectoryUnavailable("The directory has no service-account password set")
    password = await vault_service.read(
        session, owner_type=BIND_SECRET, owner_id=_CONFIG_OWNER, version=cfg.bind_secret_version
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
    )


async def save_config(
    session: AsyncSession, actor: Actor, values: dict[str, Any], bind_password: str | None
) -> DirectoryConfig:
    cfg = await session.get(DirectoryConfig, 1, with_for_update=True)
    if cfg is None:
        cfg = DirectoryConfig(id=1, **values)
        session.add(cfg)
    else:
        for key, value in values.items():
            setattr(cfg, key, value)
    if bind_password:
        current = (
            await session.execute(
                select(func.max(Secret.version)).where(
                    Secret.owner_type == BIND_SECRET, Secret.owner_id == _CONFIG_OWNER
                )
            )
        ).scalar_one()
        version = (current or 0) + 1
        await vault_service.store(
            session,
            owner_type=BIND_SECRET,
            owner_id=_CONFIG_OWNER,
            version=version,
            plaintext=bind_password,
            created_by=actor.id,
        )
        cfg.bind_secret_version = version
    if cfg.enabled and cfg.bind_secret_version is None:
        raise ConflictError("Set the service-account password before enabling the directory")
    cfg.updated_by = actor.id
    await session.flush()
    await audit_service.record(
        session,
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
        },
    )
    await session.commit()
    return cfg


async def _client(session: AsyncSession) -> DirectoryClient:
    cfg = await get_config(session)
    if cfg is None:
        raise NotFoundError("No directory is configured")
    return DirectoryClient(await _settings(session, cfg), _factory)


async def test_lookup(session: AsyncSession, actor: Actor, username: str) -> DirectoryUser:
    """Service-account lookup of one user, without their password: shows DN, groups, role."""
    client = await _client(session)
    try:
        user = await to_thread.run_sync(client.lookup, username)
    except DirectoryError as exc:
        raise DirectoryUnavailable(str(exc)) from exc
    except DirectoryAuthFailed as exc:
        raise NotFoundError(f"Lookup failed: {exc}") from exc
    finally:
        await audit_service.record(
            session,
            actor,
            "directory.test",
            object_type="directory",
            details={"username": username},
        )
        await session.commit()
    return user


async def is_enabled(session: AsyncSession) -> bool:
    cfg = await get_config(session)
    return bool(cfg and cfg.enabled)


async def authenticate(session: AsyncSession, username: str, password: str) -> DirectoryUser:
    """Raises DirectoryAuthFailed (bad credentials / no role) or DirectoryUnavailable."""
    client = await _client(session)
    try:
        return await to_thread.run_sync(client.authenticate, username, password)
    except DirectoryError as exc:
        raise DirectoryUnavailable(str(exc)) from exc


async def upsert_user(session: AsyncSession, existing: User | None, found: DirectoryUser) -> User:
    """Create or refresh the local row for a directory user (caller commits)."""
    user = existing
    if user is None:
        user = User(
            username=found.username,
            password_hash=NO_LOCAL_PASSWORD,
            auth_source="ldap",
            role=found.role,
        )
        session.add(user)
    elif user.role != found.role:
        # A role change ends existing sessions, like an admin edit would.
        user.token_version += 1
    user.role = found.role
    user.email = found.email
    user.full_name = found.full_name
    user.external_id = found.dn
    user.directory_synced_at = utcnow()
    await session.flush()
    return user
