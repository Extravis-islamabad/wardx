"""Database side of the gateway: who may connect, with which credential, and session records.

Access follows the same rules as a check-out from the console:
- the user already holds an active check-out of the account: use it;
- the account needs approval: use the user's approved request (it is spent);
- otherwise: check the account out for the session, and check it back in after.
An exclusive account held by someone else refuses the connection.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import func, or_, select, update

from src.contracts.schemas.access import CheckoutCreate
from src.core.config import Settings
from src.core.context import SYSTEM_ACTOR, Actor
from src.core.db import session_factory
from src.core.enums import CheckoutStatus, Protocol, RequestStatus, Role
from src.errors.exceptions import AppError
from src.gateway.policy import CommandPolicy
from src.models import (
    AccessRequest,
    Account,
    Checkout,
    CommandRule,
    GatewaySession,
    SessionCommand,
    Target,
    utcnow,
)
from src.services import access_service, audit_service, auth_service, mfa_service, vault_service
from src.services.inventory_service import ACCOUNT_SECRET

GATEWAY_REASON = "Interactive session via WardX gateway"
SUPPORTED_PROTOCOLS = {Protocol.SSH}


class GatewayDenied(Exception):
    """Shown to the user in their terminal; the connection then closes."""


@dataclass(frozen=True)
class TargetInfo:
    id: uuid.UUID
    name: str
    address: str
    port: int
    platform: str
    ssh_host_key: str | None


@dataclass(frozen=True)
class Grant:
    session_id: uuid.UUID
    actor: Actor
    account_id: uuid.UUID
    account_username: str
    secret_type: str
    secret: str
    target: TargetInfo
    checkout_id: uuid.UUID
    owns_checkout: bool
    expires_at: datetime
    policy: CommandPolicy


@dataclass(frozen=True)
class CloseOrder:
    status: str  # terminated | closed
    reason: str


class Broker:
    def __init__(self, settings: Settings, node: str) -> None:
        self.settings = settings
        self.node = node

    # ── Authentication ──

    async def authenticate(self, username: str, password: str, source_ip: str | None) -> Actor:
        async with session_factory()() as session:
            user = await auth_service.authenticate(
                session,
                self.settings,
                username=username,
                password=password,
                source_ip=source_ip,
                channel="ssh_gateway",
            )
            return Actor(
                id=user.id, username=user.username, role=Role(user.role), source_ip=source_ip
            )

    async def mfa_enabled(self, actor: Actor) -> bool:
        async with session_factory()() as session:
            return await mfa_service.is_enabled(session, actor.id)

    async def verify_mfa(self, actor: Actor, code: str) -> bool:
        async with session_factory()() as session:
            try:
                await mfa_service.verify_login_code(
                    session,
                    self.settings,
                    user_id=actor.id,
                    code=code,
                    source_ip=actor.source_ip,
                    channel="ssh_gateway",
                )
            except AppError:
                return False
            return True

    # ── Opening a session ──

    async def open(
        self,
        actor: Actor,
        *,
        target_name: str,
        account_username: str | None,
        mode: str,
        command: str | None,
    ) -> Grant:
        async with session_factory()() as session:
            if mfa_service.is_required(
                self.settings, actor.role
            ) and not await mfa_service.is_enabled(session, actor.id):
                raise GatewayDenied(
                    "Your role requires MFA. Set it up in the WardX console, then reconnect."
                )
            target = (
                await session.execute(
                    select(Target).where(func.lower(Target.name) == target_name.lower())
                )
            ).scalar_one_or_none()
            if target is None or not target.is_active:
                raise GatewayDenied(f"No active target named '{target_name}'")
            if target.protocol not in SUPPORTED_PROTOCOLS:
                raise GatewayDenied(
                    f"{target.name} uses {target.protocol.upper()}; this gateway proxies SSH"
                )

            accounts = (
                (await session.execute(select(Account).where(Account.target_id == target.id)))
                .scalars()
                .all()
            )
            if account_username is None:
                if len(accounts) != 1:
                    names = ", ".join(sorted(a.username for a in accounts)) or "none"
                    raise GatewayDenied(
                        f"{target.name} has several accounts ({names}); "
                        f"connect as you%account%{target.name}"
                    )
                account = accounts[0]
            else:
                account = next((a for a in accounts if a.username == account_username), None)
                if account is None:
                    raise GatewayDenied(f"No account '{account_username}' on {target.name}")

            checkout, owns = await self._obtain_checkout(session, actor, account)
            try:
                secret = await vault_service.read(
                    session,
                    owner_type=ACCOUNT_SECRET,
                    owner_id=account.id,
                    version=account.secret_version,
                )
            except AppError as exc:
                if owns:
                    await self._close_checkout(checkout.id, actor)
                raise GatewayDenied(f"Credential unavailable: {exc.message}") from exc

            rules = (
                await session.execute(
                    select(CommandRule.id, CommandRule.pattern, CommandRule.description).where(
                        CommandRule.is_active,
                        or_(CommandRule.account_id.is_(None), CommandRule.account_id == account.id),
                        or_(CommandRule.target_id.is_(None), CommandRule.target_id == target.id),
                        or_(
                            CommandRule.platform.is_(None), CommandRule.platform == target.platform
                        ),
                    )
                )
            ).all()

            row = GatewaySession(
                checkout_id=checkout.id,
                user_id=actor.id,
                account_id=account.id,
                target_id=target.id,
                account_username=account.username,
                target_name=target.name,
                target_address=target.address,
                protocol=target.protocol,
                mode=mode,
                exec_command=command,
                client_ip=actor.source_ip,
                gateway_node=self.node,
                status="active",
                started_at=utcnow(),
            )
            session.add(row)
            await session.flush()
            await audit_service.record(
                session,
                actor,
                "session.start",
                object_type="session",
                object_id=row.id,
                details={
                    "account_id": str(account.id),
                    "target": target.name,
                    "mode": mode,
                    "command": command,
                    "checkout_id": str(checkout.id),
                    "gateway": self.node,
                },
            )
            await audit_service.record(
                session,
                actor,
                "secret.inject",
                object_type="session",
                object_id=row.id,
                details={"account_id": str(account.id), "version": account.secret_version},
            )
            await session.commit()
            return Grant(
                session_id=row.id,
                actor=actor,
                account_id=account.id,
                account_username=account.username,
                secret_type=account.secret_type,
                secret=secret,
                target=TargetInfo(
                    target.id,
                    target.name,
                    target.address,
                    target.port,
                    target.platform,
                    target.ssh_host_key,
                ),
                checkout_id=checkout.id,
                owns_checkout=owns,
                expires_at=checkout.expires_at,
                policy=CommandPolicy.build(rules),
            )

    async def _obtain_checkout(
        self, session, actor: Actor, account: Account
    ) -> tuple[Checkout, bool]:
        held = (
            (
                await session.execute(
                    select(Checkout).where(
                        Checkout.account_id == account.id,
                        Checkout.user_id == actor.id,
                        Checkout.status == CheckoutStatus.ACTIVE,
                        Checkout.expires_at > utcnow(),
                    )
                )
            )
            .unique()
            .scalar_one_or_none()
        )
        if held is not None:
            return held, False

        body = CheckoutCreate(account_id=account.id, reason=GATEWAY_REASON)
        if account.requires_approval:
            request = (
                (
                    await session.execute(
                        select(AccessRequest)
                        .where(
                            AccessRequest.account_id == account.id,
                            AccessRequest.requester_id == actor.id,
                            AccessRequest.status == RequestStatus.APPROVED,
                            AccessRequest.expires_at > utcnow(),
                        )
                        .order_by(AccessRequest.decided_at.desc())
                        .limit(1)
                    )
                )
                .unique()
                .scalar_one_or_none()
            )
            if request is None:
                raise GatewayDenied(
                    f"{account.username} needs an approved request. Request access in the "
                    "WardX console, then reconnect once it is approved."
                )
            body = CheckoutCreate(account_id=account.id, request_id=request.id)
        try:
            out = await access_service.checkout(session, actor, body)
        except AppError as exc:
            held_by = exc.details.get("held_by")
            suffix = f" (held by {held_by} until {exc.details.get('until')})" if held_by else ""
            raise GatewayDenied(exc.message + suffix) from exc
        checkout = await session.get(Checkout, out.id)
        return checkout, True

    # ── During a session ──

    async def pin_host_key(self, grant: Grant, key: str, fingerprint: str) -> bool:
        """Store a target's first-seen host key. False if another key got pinned first."""
        async with session_factory()() as session:
            result = await session.execute(
                update(Target)
                .where(Target.id == grant.target.id, Target.ssh_host_key.is_(None))
                .values(
                    ssh_host_key=key,
                    ssh_host_key_fingerprint=fingerprint,
                    ssh_host_key_learned_at=utcnow(),
                )
            )
            if result.rowcount == 0:
                await session.rollback()
                return False
            await audit_service.record(
                session,
                grant.actor,
                "target.host_key_learned",
                object_type="target",
                object_id=grant.target.id,
                details={"fingerprint": fingerprint, "session_id": str(grant.session_id)},
            )
            await session.commit()
            return True

    async def host_key_mismatch(self, grant: Grant, presented: str | None) -> None:
        async with session_factory()() as session:
            await audit_service.record(
                session,
                grant.actor,
                "target.host_key_mismatch",
                object_type="target",
                object_id=grant.target.id,
                outcome="failure",
                details={"presented_fingerprint": presented, "session_id": str(grant.session_id)},
            )
            await session.commit()

    async def record_command(
        self,
        grant: Grant,
        *,
        offset: float,
        command: str,
        blocked_rule: uuid.UUID | None,
        blocked: bool,
        edited: bool,
    ) -> None:
        async with session_factory()() as session:
            session.add(
                SessionCommand(
                    session_id=grant.session_id,
                    occurred_at=utcnow(),
                    offset_seconds=offset,
                    command=command + (" ⟨edited⟩" if edited else ""),
                    verdict="blocked" if blocked else "allowed",
                    rule_id=blocked_rule,
                )
            )
            counters = {"commands_count": GatewaySession.commands_count + 1}
            if blocked:
                counters["blocked_count"] = GatewaySession.blocked_count + 1
                await audit_service.record(
                    session,
                    grant.actor,
                    "session.command_blocked",
                    object_type="session",
                    object_id=grant.session_id,
                    outcome="failure",
                    details={"command": command, "rule_id": str(blocked_rule)},
                )
            await session.execute(
                update(GatewaySession)
                .where(GatewaySession.id == grant.session_id)
                .values(**counters)
            )
            await session.commit()

    async def close_orders(self, grants: list[Grant]) -> dict[uuid.UUID, CloseOrder]:
        """Sessions that must end now: kill requested, or their check-out is over."""
        if not grants:
            return {}
        by_session = {g.session_id: g for g in grants}
        async with session_factory()() as session:
            rows = (
                await session.execute(
                    select(
                        GatewaySession.id,
                        GatewaySession.terminate_requested_at,
                        GatewaySession.close_reason,
                        Checkout.status,
                        Checkout.expires_at,
                    )
                    .join(Checkout, Checkout.id == GatewaySession.checkout_id, isouter=True)
                    .where(GatewaySession.id.in_(by_session))
                )
            ).all()
        now = utcnow()
        orders: dict[uuid.UUID, CloseOrder] = {}
        for sid, kill_at, kill_reason, co_status, co_expires in rows:
            if kill_at is not None:
                # A reason set with the kill request (e.g. by directory sync) is shown as is.
                orders[sid] = CloseOrder(
                    "terminated", kill_reason or "Terminated by an administrator"
                )
            elif co_status is None or co_status != CheckoutStatus.ACTIVE:
                orders[sid] = CloseOrder("terminated", "The check-out was closed")
            elif co_expires <= now:
                orders[sid] = CloseOrder("closed", "The check-out expired")
        return orders

    # ── Closing ──

    async def finish(
        self,
        grant: Grant,
        *,
        status: str,
        reason: str,
        recording_path: str | None,
        recording_sha256: str | None,
        recording_bytes: int | None,
        bytes_from_target: int,
        bytes_from_user: int,
    ) -> None:
        async with session_factory()() as session:
            await session.execute(
                update(GatewaySession)
                .where(GatewaySession.id == grant.session_id, GatewaySession.status == "active")
                .values(
                    status=status,
                    ended_at=utcnow(),
                    close_reason=reason,
                    recording_path=recording_path,
                    recording_sha256=recording_sha256,
                    recording_bytes=recording_bytes,
                    bytes_from_target=bytes_from_target,
                    bytes_from_user=bytes_from_user,
                )
            )
            await audit_service.record(
                session,
                grant.actor,
                "session.end",
                object_type="session",
                object_id=grant.session_id,
                outcome="success" if status in ("closed", "terminated") else "failure",
                details={
                    "status": status,
                    "reason": reason,
                    "recording_sha256": recording_sha256,
                    "bytes_from_target": bytes_from_target,
                },
            )
            await session.commit()
        if grant.owns_checkout:
            await self._close_checkout(grant.checkout_id, grant.actor)

    async def _close_checkout(self, checkout_id: uuid.UUID, actor: Actor) -> None:
        async with session_factory()() as session:
            try:
                await access_service.checkin(session, actor, checkout_id)
            except AppError:
                # Already expired, revoked or returned: nothing to close.
                await session.rollback()

    async def recover_orphans(self) -> int:
        """Sessions left 'active' by a previous run of this gateway node."""
        async with session_factory()() as session:
            ids = (
                await session.execute(
                    update(GatewaySession)
                    .where(
                        GatewaySession.status == "active", GatewaySession.gateway_node == self.node
                    )
                    .values(status="failed", ended_at=utcnow(), close_reason="Gateway restarted")
                    .returning(
                        GatewaySession.id, GatewaySession.checkout_id, GatewaySession.user_id
                    )
                )
            ).all()
            for sid, _checkout_id, _user_id in ids:
                await audit_service.record(
                    session,
                    SYSTEM_ACTOR,
                    "session.end",
                    object_type="session",
                    object_id=sid,
                    outcome="failure",
                    details={"status": "failed", "reason": "Gateway restarted"},
                )
            await session.commit()
            # Their check-outs keep their own expiry; the sweeper closes them.
            return len(ids)
