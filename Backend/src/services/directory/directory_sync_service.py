"""Scheduled directory sync: apply leavers and role changes without waiting for a sign-in.

Every directory user (auth_source 'ldap') is looked up with the service
account. Someone no longer in the directory, or in no mapped group, is
disabled at once: tokens revoked, active check-outs revoked, live gateway
sessions killed. Role and profile changes are applied.

Guard rails:
- Directory unreachable, or the service account fails: nothing changes.
- A login name matching several entries is reported, never disabled.
- A run that would disable more than ``sync_max_disable_percent`` of the
  directory users stops without changes (``needs_review``) — a typo in the
  search base must not lock everybody out. An admin can re-run with force.
- Only accounts the sync disabled itself are re-enabled; an administrator's
  decision to disable someone is never overridden.

Every applied run also refreshes the group cache (safe memberships by directory
group) of each user it found, and removes it for users it disables. The run's
outcome is recorded as the directory's reachability.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta

from anyio import to_thread

from src.contracts.dto.directory.directory_sync_dto import SyncResultDTO
from src.contracts.dto.identity.user_dto import UserDTO
from src.core.context import SYSTEM_ACTOR, Actor
from src.directory.ldap_client import (
    AmbiguousUser,
    DirectoryClient,
    DirectoryError,
    DirectoryUser,
    UserNotFound,
    normalise_dn,
)
from src.errors.exceptions import ConflictError, DirectoryUnavailable
from src.models import utcnow
from src.repositories.access.checkout_repository import CheckoutRepository
from src.repositories.directory.directory_config_repository import DirectoryConfigRepository
from src.repositories.identity.group_cache_repository import GroupCacheRepository
from src.repositories.identity.user_repository import UserRepository
from src.repositories.sessions.gateway_session_repository import GatewaySessionRepository
from src.services.audit.audit_service import AuditService
from src.services.directory.directory_service import SYNC_DISABLED, DirectoryService

SYNC_LOCK_KEY = 0x5741_5244_00D5


@dataclass
class _Plan:
    disable: list[tuple[UserDTO, str]] = field(default_factory=list)
    enable: list[tuple[UserDTO, DirectoryUser]] = field(default_factory=list)
    refresh: list[tuple[UserDTO, DirectoryUser]] = field(default_factory=list)
    # Every active or re-enabled user found in the directory, for the group cache.
    found: list[tuple[UserDTO, DirectoryUser]] = field(default_factory=list)


def _changed(user: UserDTO, found: DirectoryUser) -> bool:
    return (user.role, user.email, user.full_name, user.external_id) != (
        found.role,
        found.email,
        found.full_name,
        found.dn,
    )


async def _plan(client: DirectoryClient, users: list[UserDTO], result: SyncResultDTO) -> _Plan:
    plan = _Plan()
    for user in users:
        result.checked += 1
        try:
            found = await to_thread.run_sync(client.lookup, user.username)
        except UserNotFound:
            if user.is_active:
                plan.disable.append((user, "not in directory"))
            continue
        except AmbiguousUser:
            result.problems.append(f"{user.username}: several directory entries match; skipped")
            continue
        if found.role is None:
            if user.is_active:
                plan.disable.append((user, "in no mapped group"))
            continue
        if not user.is_active:
            if user.disabled_reason == SYNC_DISABLED:
                plan.enable.append((user, found))
                plan.found.append((user, found))
            continue
        plan.found.append((user, found))
        if _changed(user, found):
            plan.refresh.append((user, found))
    return plan


class DirectorySyncService:
    def __init__(
        self,
        directory: DirectoryService,
        config: DirectoryConfigRepository,
        users: UserRepository,
        checkouts: CheckoutRepository,
        sessions: GatewaySessionRepository,
        audit: AuditService,
        group_cache: GroupCacheRepository,
    ) -> None:
        self._directory = directory
        self._config = config
        self._users = users
        self._checkouts = checkouts
        self._sessions = sessions
        self._audit = audit
        self._group_cache = group_cache

    async def sync_due(self) -> bool:
        cfg = await self._config.get()
        if cfg is None or not cfg.enabled or cfg.sync_interval_minutes == 0:
            return False
        if cfg.last_sync_at is None:
            return True
        return utcnow() - cfg.last_sync_at >= timedelta(minutes=cfg.sync_interval_minutes)

    async def run_sync(
        self, *, actor: Actor = SYSTEM_ACTOR, dry_run: bool = False, force: bool = False
    ) -> SyncResultDTO:
        if not await self._config.try_advisory_lock(SYNC_LOCK_KEY):
            raise ConflictError("A directory sync is already running")
        cfg = await self._config.get()
        if cfg is None or not cfg.enabled:
            raise ConflictError("Directory sign-in is not enabled")

        result = SyncResultDTO(dry_run=dry_run)
        # No row locks: lookups can be slow and would stall these users' sign-ins.
        users = await self._users.directory_users()
        try:
            client = await self._directory.client()
            plan = await _plan(client, users, result)
        except (DirectoryError, DirectoryUnavailable) as exc:
            result.status = "failed"
            result.problems.append(f"Directory unavailable; nothing changed: {exc}")
            plan = _Plan()
            unreachable: str | None = str(exc)
        else:
            unreachable = None

        active = sum(1 for u in users if u.is_active)
        share = (len(plan.disable) * 100 / active) if active else 0
        if (
            result.status == "ok"
            and plan.disable
            and share > cfg.sync_max_disable_percent
            and not force
        ):
            result.status = "needs_review"
            result.problems.append(
                f"Would disable {len(plan.disable)} of {active} directory users ({share:.0f}%), "
                f"over the {cfg.sync_max_disable_percent}% limit. Check the search base and group "
                "mappings, then run again with force if this is intended."
            )
        result.disabled = [{"username": u.username, "reason": r} for u, r in plan.disable]
        result.enabled = [u.username for u, _ in plan.enable]
        result.role_changes = [
            {"username": u.username, "from": u.role, "to": f.role}
            for u, f in plan.refresh
            if u.role != f.role
        ]
        result.profile_updates = len(plan.refresh)

        if result.status == "ok" and not dry_run:
            await self._apply(plan, actor, result)

        now = utcnow()
        reachability = {
            "reachable": unreachable is None,
            "reachability_checked_at": now,
            "reachability_error": unreachable[:500] if unreachable else None,
        }
        if not dry_run:
            await self._config.save(
                {
                    "last_sync_at": now,
                    "last_sync_status": result.status,
                    "last_sync_summary": result.summary(),
                    **reachability,
                }
            )
        else:
            await self._config.save(reachability)
        await self._audit.record(
            actor,
            "directory.sync",
            object_type="directory",
            outcome="success" if result.status == "ok" else "failure",
            details={
                "status": result.status,
                "dry_run": dry_run,
                "force": force,
                "checked": result.checked,
                "disabled": len(result.disabled),
                "enabled": len(result.enabled),
                "role_changes": len(result.role_changes),
            },
        )
        await self._config.commit()
        return result

    async def _apply(self, plan: _Plan, actor: Actor, result: SyncResultDTO) -> None:
        for user, reason in plan.disable:
            await self._users.update(
                user.id,
                {
                    "is_active": False,
                    "disabled_reason": SYNC_DISABLED,
                    "token_version": user.token_version + 1,
                },
            )
            await self._cut_off(user, actor, result)
            await self._group_cache.clear(user.id)
            await self._audit.record(
                actor,
                "user.disable",
                object_type="user",
                object_id=user.id,
                details={"reason": reason, "source": "directory_sync"},
            )
        for user, found in [*plan.enable, *plan.refresh]:
            await self._directory.upsert_user(user, found)
        now = utcnow()
        for user, found in plan.found:
            await self._group_cache.store(user.id, (normalise_dn(g) for g in found.groups), now)
        for user, _ in plan.enable:
            await self._audit.record(
                actor,
                "user.enable",
                object_type="user",
                object_id=user.id,
                details={"source": "directory_sync"},
            )

    async def _cut_off(self, user: UserDTO, actor: Actor, result: SyncResultDTO) -> None:
        """End everything the user holds right now."""
        now = utcnow()
        revoked = await self._checkouts.revoke_active_for_user(user.id, now)
        for checkout_id in revoked:
            await self._audit.record(
                actor,
                "checkout.revoke",
                object_type="checkout",
                object_id=checkout_id,
                details={"reason": "directory sync disabled the user", "user": user.username},
            )
        killed = await self._sessions.request_kill_for_user(
            user.id, now, "Access removed: you are no longer in the directory"
        )
        for session_id in killed:
            await self._audit.record(
                actor,
                "session.terminate",
                object_type="session",
                object_id=session_id,
                details={"reason": "directory sync disabled the user", "user": user.username},
            )
        result.revoked_checkouts += len(revoked)
        result.killed_sessions += len(killed)
