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
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any

from anyio import to_thread
from sqlalchemy import select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.context import SYSTEM_ACTOR, Actor
from src.core.enums import CheckoutStatus
from src.directory.ldap_client import (
    AmbiguousUser,
    DirectoryClient,
    DirectoryError,
    DirectoryUser,
    UserNotFound,
)
from src.errors.exceptions import ConflictError
from src.models import Checkout, GatewaySession, User, utcnow
from src.services import audit_service, directory_service

SYNC_LOCK_KEY = 0x5741_5244_00D5
SYNC_DISABLED = "directory_sync"


@dataclass
class SyncResult:
    status: str = "ok"  # ok | needs_review | failed
    dry_run: bool = False
    checked: int = 0
    disabled: list[dict[str, str]] = field(default_factory=list)
    enabled: list[str] = field(default_factory=list)
    role_changes: list[dict[str, str]] = field(default_factory=list)
    profile_updates: int = 0
    problems: list[str] = field(default_factory=list)
    revoked_checkouts: int = 0
    killed_sessions: int = 0

    def summary(self) -> dict[str, Any]:
        return self.__dict__.copy()


@dataclass
class _Plan:
    disable: list[tuple[User, str]] = field(default_factory=list)
    enable: list[tuple[User, DirectoryUser]] = field(default_factory=list)
    refresh: list[tuple[User, DirectoryUser]] = field(default_factory=list)


def _changed(user: User, found: DirectoryUser) -> bool:
    return (user.role, user.email, user.full_name, user.external_id) != (
        found.role,
        found.email,
        found.full_name,
        found.dn,
    )


async def _plan(client: DirectoryClient, users: list[User], result: SyncResult) -> _Plan:
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
            continue
        if _changed(user, found):
            plan.refresh.append((user, found))
    return plan


async def _cut_off(session: AsyncSession, user: User, actor: Actor, result: SyncResult) -> None:
    """End everything the user holds right now."""
    now = utcnow()
    revoked = (
        (
            await session.execute(
                update(Checkout)
                .where(Checkout.user_id == user.id, Checkout.status == CheckoutStatus.ACTIVE)
                .values(status=CheckoutStatus.REVOKED, checked_in_at=now)
                .returning(Checkout.id)
            )
        )
        .scalars()
        .all()
    )
    for checkout_id in revoked:
        await audit_service.record(
            session,
            actor,
            "checkout.revoke",
            object_type="checkout",
            object_id=checkout_id,
            details={"reason": "directory sync disabled the user", "user": user.username},
        )
    killed = (
        (
            await session.execute(
                update(GatewaySession)
                .where(
                    GatewaySession.user_id == user.id,
                    GatewaySession.status == "active",
                    GatewaySession.terminate_requested_at.is_(None),
                )
                .values(
                    terminate_requested_at=now,
                    close_reason="Access removed: you are no longer in the directory",
                )
                .returning(GatewaySession.id)
            )
        )
        .scalars()
        .all()
    )
    for session_id in killed:
        await audit_service.record(
            session,
            actor,
            "session.terminate",
            object_type="session",
            object_id=session_id,
            details={"reason": "directory sync disabled the user", "user": user.username},
        )
    result.revoked_checkouts += len(revoked)
    result.killed_sessions += len(killed)


async def run_sync(
    session: AsyncSession,
    *,
    actor: Actor = SYSTEM_ACTOR,
    dry_run: bool = False,
    force: bool = False,
) -> SyncResult:
    got = (
        await session.execute(text("SELECT pg_try_advisory_xact_lock(:k)"), {"k": SYNC_LOCK_KEY})
    ).scalar_one()
    if not got:
        raise ConflictError("A directory sync is already running")
    cfg = await directory_service.get_config(session)
    if cfg is None or not cfg.enabled:
        raise ConflictError("Directory sign-in is not enabled")

    result = SyncResult(dry_run=dry_run)
    users = list(
        (
            await session.execute(
                # No row locks: lookups can be slow and would stall these users' sign-ins.
                select(User).where(User.auth_source == "ldap").order_by(User.username)
            )
        ).scalars()
    )
    try:
        client = await directory_service._client(session)
        plan = await _plan(client, users, result)
    except (DirectoryError, directory_service.DirectoryUnavailable) as exc:
        result.status = "failed"
        result.problems.append(f"Directory unavailable; nothing changed: {exc}")
        plan = _Plan()

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
            f"Would disable {len(plan.disable)} of {active} directory users ({share:.0f}%), over "
            f"the {cfg.sync_max_disable_percent}% limit. Check the search base and group mappings, "
            "then run again with force if this is intended."
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
        for user, reason in plan.disable:
            user.is_active = False
            user.disabled_reason = SYNC_DISABLED
            user.token_version += 1
            await _cut_off(session, user, actor, result)
            await audit_service.record(
                session,
                actor,
                "user.disable",
                object_type="user",
                object_id=user.id,
                details={"reason": reason, "source": "directory_sync"},
            )
        for user, found in [*plan.enable, *plan.refresh]:
            await directory_service.upsert_user(session, user, found)
        for user, _ in plan.enable:
            await audit_service.record(
                session,
                actor,
                "user.enable",
                object_type="user",
                object_id=user.id,
                details={"source": "directory_sync"},
            )

    if not dry_run:
        cfg.last_sync_at = utcnow()
        cfg.last_sync_status = result.status
        cfg.last_sync_summary = result.summary()
    await audit_service.record(
        session,
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
    await session.commit()
    return result


async def sync_due(session: AsyncSession) -> bool:
    cfg = await directory_service.get_config(session)
    if cfg is None or not cfg.enabled or cfg.sync_interval_minutes == 0:
        return False
    if cfg.last_sync_at is None:
        return True
    return utcnow() - cfg.last_sync_at >= timedelta(minutes=cfg.sync_interval_minutes)
