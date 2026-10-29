"""Database side of the gateway: who may connect, with which credential, and session records.

Access follows the same rules as a check-out from the console, except that a
session needs ``use`` or ``retrieve`` on the account's safe (``use`` connects
without ever showing the password). Accounts in safes the user cannot list do
not exist for them here either. Then:

- the user already holds an active check-out of the account: use it;
- the account needs approval: use the user's approved request (it is spent);
- otherwise: check the account out for the session, and check it back in after.
An exclusive account held by someone else refuses the connection.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from src.contracts.dto.access.checkout_dto import CheckoutDTO
from src.contracts.dto.inventory.account_dto import AccountDTO
from src.contracts.dto.sessions.command_rule_dto import RuleScopeDTO
from src.core.config import Settings
from src.core.context import Actor
from src.core.db import session_factory
from src.core.enums import CheckoutStatus, KeyPurpose, Protocol, Role, SafePermission
from src.dependencies.access import build_access_request_service, build_checkout_service
from src.dependencies.identity import build_auth_service, build_mfa_service
from src.dependencies.inventory import build_account_service, build_target_service
from src.dependencies.keys import build_tenant_key_service
from src.dependencies.rotation import build_rotation_guard
from src.dependencies.safes import build_safe_access_service
from src.dependencies.sessions import (
    build_command_rule_service,
    build_gateway_node_service,
    build_gateway_session_service,
    build_host_key_service,
)
from src.dependencies.vault import build_vault_service
from src.errors.exceptions import AppError
from src.gateway.policy import CommandPolicy
from src.models import utcnow
from src.services.inventory.account_service import ACCOUNT_SECRET

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
            user = await build_auth_service(session).authenticate(
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
            return await build_mfa_service(session).is_enabled(actor.id)

    async def verify_mfa(self, actor: Actor, code: str) -> bool:
        async with session_factory()() as session:
            try:
                await build_mfa_service(session).verify_login_code(
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
            mfa = build_mfa_service(session)
            if mfa.is_required(actor.role) and not await mfa.is_enabled(actor.id):
                raise GatewayDenied(
                    "Your role requires MFA. Set it up in the WardX console, then reconnect."
                )
            target = await build_target_service(session).find_by_name(target_name)
            if target is None or not target.is_active:
                raise GatewayDenied(f"No active target named '{target_name}'")
            if target.protocol not in SUPPORTED_PROTOCOLS:
                raise GatewayDenied(
                    f"{target.name} uses {target.protocol.upper()}; this gateway proxies SSH"
                )

            access = build_safe_access_service(session)
            listable = await access.listable_safe_ids(actor)
            accounts = [
                a
                for a in await build_account_service(session).list_for_target(target.id)
                if a.safe_id in listable
            ]
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
            perms = await access.permissions(actor, account.safe_id)
            if not perms & {SafePermission.USE, SafePermission.RETRIEVE}:
                raise GatewayDenied(
                    f"You may not connect as {account.username} on {target.name} "
                    "(needs 'use' or 'retrieve' on its safe)"
                )

            try:
                await build_rotation_guard(session).ensure_normal_access(account.id)
            except AppError as exc:
                raise GatewayDenied(exc.message) from exc
            checkout, owns = await self._obtain_checkout(session, actor, account)
            try:
                secret = await build_vault_service(session).read(
                    owner_type=ACCOUNT_SECRET,
                    owner_id=account.id,
                    version=account.secret_version,
                )
            except AppError as exc:
                if owns:
                    await self._close_checkout(checkout.id, actor)
                raise GatewayDenied(f"Credential unavailable: {exc.message}") from exc

            policy = await build_command_rule_service(session).policy_for(
                RuleScopeDTO(account_id=account.id, target_id=target.id, platform=target.platform)
            )
            session_id = await build_gateway_session_service(session).start(
                actor,
                checkout_id=checkout.id,
                account=account,
                target=target,
                mode=mode,
                command=command,
                node=self.node,
                owns_checkout=owns,
            )
            return Grant(
                session_id=session_id,
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
                policy=policy,
            )

    async def _obtain_checkout(
        self, session: AsyncSession, actor: Actor, account: AccountDTO
    ) -> tuple[CheckoutDTO, bool]:
        checkouts = build_checkout_service(session)
        held = await checkouts.held_by(actor, account.id)
        if held is not None:
            return held, False

        body: dict = {"account_id": account.id, "reason": GATEWAY_REASON, "for_session": True}
        if account.requires_approval:
            request = await build_access_request_service(session).usable_approval(actor, account.id)
            if request is None:
                raise GatewayDenied(
                    f"{account.username} needs an approved request. Request access in the "
                    "WardX console, then reconnect once it is approved."
                )
            body = {"account_id": account.id, "request_id": request.id, "for_session": True}
        try:
            out = await checkouts.checkout(actor, **body)
        except AppError as exc:
            held_by = exc.details.get("held_by")
            suffix = f" (held by {held_by} until {exc.details.get('until')})" if held_by else ""
            raise GatewayDenied(exc.message + suffix) from exc
        return out, True

    # ── During a session ──

    async def pin_host_key(self, grant: Grant, key: str, fingerprint: str) -> bool:
        """Store a target's first-seen host key. False if another key got pinned first."""
        async with session_factory()() as session:
            return await build_host_key_service(session).pin(
                grant.actor,
                grant.target.id,
                key=key,
                fingerprint=fingerprint,
                session_id=grant.session_id,
            )

    async def host_key_mismatch(self, grant: Grant, presented: str | None) -> None:
        async with session_factory()() as session:
            await build_host_key_service(session).record_mismatch(
                grant.actor, grant.target.id, presented=presented, session_id=grant.session_id
            )

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
            await build_gateway_session_service(session).record_command(
                grant.actor,
                grant.session_id,
                offset=offset,
                command=command,
                blocked_rule=blocked_rule,
                blocked=blocked,
                edited=edited,
            )

    async def close_orders(self, grants: list[Grant]) -> dict[uuid.UUID, CloseOrder]:
        """Sessions that must end now: kill requested, or their check-out is over."""
        if not grants:
            return {}
        by_session = {g.session_id: g for g in grants}
        async with session_factory()() as session:
            rows = await build_gateway_session_service(session).close_state(list(by_session))
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
        recording: dict | None = None,
    ) -> None:
        async with session_factory()() as session:
            await build_gateway_session_service(session).finish(
                grant.actor,
                grant.session_id,
                status=status,
                reason=reason,
                recording_path=recording_path,
                recording_sha256=recording_sha256,
                recording_bytes=recording_bytes,
                bytes_from_target=bytes_from_target,
                bytes_from_user=bytes_from_user,
                recording=recording,
            )
        if grant.owns_checkout:
            await self._close_checkout(grant.checkout_id, grant.actor)

    async def _close_checkout(self, checkout_id: uuid.UUID, actor: Actor) -> None:
        async with session_factory()() as session:
            try:
                await build_checkout_service(session).checkin(actor, checkout_id)
            except AppError:
                # Already expired, revoked or returned: nothing to close.
                await session.rollback()

    # ── Node liveness (HA_DR.md §5) ──

    async def register_node(self, fingerprint: str) -> None:
        """Raises HostKeyConflict when this node's host key is not the cluster's."""
        async with session_factory()() as session:
            await build_gateway_node_service(session).register(
                self.node,
                fingerprint,
                expected=self.settings.gateway_host_key_fingerprint,
                lost_after=self.settings.gateway_lost_seconds,
            )

    async def heartbeat(self) -> None:
        async with session_factory()() as session:
            await build_gateway_node_service(session).heartbeat(self.node)

    async def node_stopped(self) -> None:
        async with session_factory()() as session:
            await build_gateway_node_service(session).stopped(self.node)

    async def recover_orphans(self, salvage) -> int:
        """Sessions left 'active' by a previous run of this gateway node: ended as failed,
        their partial recordings salvaged, their own check-outs closed."""
        async with session_factory()() as session:
            return await build_gateway_node_service(session).recover_node(self.node, salvage)

    async def files_key(self) -> tuple[int, bytes]:
        """The tenant's active ``files`` key (version, key) for recording encryption."""
        async with session_factory()() as session:
            return await build_tenant_key_service(session).active(KeyPurpose.FILES)
