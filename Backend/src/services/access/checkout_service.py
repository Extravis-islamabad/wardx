"""Check-out, reveal, check-in and expiry of privileged account credentials.

Rules:
- Check-out and reveal need ``retrieve`` on the account's safe; a check-out the
  gateway takes for a session needs ``use`` or ``retrieve``. An account in a
  safe the caller cannot list reads as 404.
- An account whose safe requires approval is checked out only against an approved
  request of the same person, within its window (see AccessRequestService). A
  single-use approval becomes ``used``; a multi-use one counts uses until it expires.
- An exclusive account has at most one active check-out at a time. The account
  row lock serialises competing check-outs, so two people cannot both win.
- Only the holder reveals the secret, and only while the check-out is active.
  The holder checks in (returned); anyone else needs ACCESS_REVOKE (revoked).
- Check-outs and requests past their time are expired, by the scheduler's sweep
  and lazily before each check-out of the account.
- Every decision, check-out, reveal and check-in is audited in the same
  transaction as the change it records.
- Rotation (docs/phase1/ROTATION.md): a pending, running or attention-needing rotation,
  or an untrustworthy verify, refuses new check-outs (RotationGuard). When a check-out
  ends (check-in, revoke, expiry) on an account that rotates after use, the rotation is
  queued, waiting for every holder to release the account.
"""

from __future__ import annotations

import uuid
from datetime import timedelta

from src.contracts.dto.access.access_request_dto import AccessRequestDTO
from src.contracts.dto.access.checkout_dto import (
    CheckoutDTO,
    CheckoutFilterDTO,
    RevealedSecretDTO,
)
from src.contracts.dto.safes.approval_policy_dto import RequestPolicyDTO
from src.core.context import SYSTEM_ACTOR, Actor
from src.core.enums import CheckoutStatus, RequestStatus, SafePermission
from src.core.permissions import ACCESS_REVOKE, ACCESS_VIEW_ALL
from src.errors.exceptions import ConflictError, ForbiddenError, NotFoundError
from src.models import utcnow
from src.repositories.access.access_request_repository import AccessRequestRepository
from src.repositories.access.checkout_repository import CheckoutRepository
from src.services.audit.audit_service import AuditService
from src.services.inventory.account_service import ACCOUNT_SECRET, AccountService
from src.services.notify.notification_service import NotificationService
from src.services.rotation.rotation_guard import RotationGuard
from src.services.vault.vault_service import VaultService

EXPIRY_LOCK_KEY = 0x5741_5244_00E1


class CheckoutService:
    def __init__(
        self,
        checkouts: CheckoutRepository,
        requests: AccessRequestRepository,
        accounts: AccountService,
        vault: VaultService,
        audit: AuditService,
        notifications: NotificationService,
        rotation: RotationGuard,
    ) -> None:
        self._checkouts = checkouts
        self._rotation = rotation
        self._requests = requests
        self._accounts = accounts
        self._vault = vault
        self._audit = audit
        self._notify = notifications

    async def list(
        self,
        actor: Actor,
        *,
        page: int,
        page_size: int,
        status: str | None = None,
        mine: bool = False,
    ) -> tuple[list[CheckoutDTO], int]:
        own = mine or not actor.can(ACCESS_VIEW_ALL)
        return await self._checkouts.list(
            CheckoutFilterDTO(user_id=actor.id if own else None, status=status),
            page=page,
            page_size=page_size,
        )

    async def get(self, checkout_id: uuid.UUID, *, lock: bool = False) -> CheckoutDTO:
        co = await self._checkouts.get(checkout_id, lock=lock)
        if co is None:
            raise NotFoundError("Check-out not found")
        return co

    async def held_by(self, actor: Actor, account_id: uuid.UUID) -> CheckoutDTO | None:
        """The actor's own active, unexpired check-out of the account, if any."""
        return await self._checkouts.active_held(account_id, actor.id, utcnow())

    async def checkout(
        self,
        actor: Actor,
        *,
        account_id: uuid.UUID,
        reason: str | None = None,
        duration_minutes: int | None = None,
        request_id: uuid.UUID | None = None,
        for_session: bool = False,
    ) -> CheckoutDTO:
        account = await self._accounts.get(account_id, lock=True)
        needed = (
            (SafePermission.USE, SafePermission.RETRIEVE)
            if for_session
            else (SafePermission.RETRIEVE,)
        )
        await self._accounts.authorise(actor, account, *needed)
        if account.secret_version == 0:
            raise ConflictError("No secret is stored for this account yet")
        await self._rotation.ensure_normal_access(account.id)
        now = utcnow()

        request: AccessRequestDTO | None = None
        if account.requires_approval:
            if request_id is None:
                raise ForbiddenError("This account requires an approved request")
            request = await self._requests.get(request_id, lock=True)
            if request is None:
                raise NotFoundError("Request not found")
            if request.requester_id != actor.id or request.account_id != account.id:
                raise ForbiddenError("That request is not yours for this account")
            if request.status != RequestStatus.APPROVED:
                raise ConflictError(f"Request is {request.status}, not approved")
            if request.expires_at <= now:
                await self._requests.update(request.id, {"status": RequestStatus.EXPIRED})
                await self._audit.record(
                    SYSTEM_ACTOR,
                    "request.expire",
                    object_type="request",
                    object_id=request.id,
                    safe_id=account.safe_id,
                )
                await self._notify.notify(
                    [request.requester_id],
                    kind="request.expired",
                    title="Your access request expired",
                    object_type="request",
                    object_id=request.id,
                )
                await self._requests.commit()
                raise ConflictError("The approval has expired; submit a new request")
            duration = request.duration_minutes
            reason = request.reason
        else:
            duration = duration_minutes or min(60, account.max_checkout_minutes)
            if duration > account.max_checkout_minutes:
                raise ConflictError(
                    f"Duration exceeds this account's limit of "
                    f"{account.max_checkout_minutes} minutes"
                )
            if not reason or len(reason.strip()) < 3:
                raise ConflictError("A reason is required to check out a credential")
            reason = reason.strip()

        # Close check-outs whose time ran out but the sweeper has not reached yet.
        await self._expire_checkouts(account_id=account.id)
        holders = await self._checkouts.active_for_account(account.id)
        if any(h.user_id == actor.id for h in holders):
            raise ConflictError("You already have this account checked out")
        if account.exclusive_checkout and holders:
            raise ConflictError(
                "Account is checked out by someone else",
                {"held_by": holders[0].user.username, "until": holders[0].expires_at.isoformat()},
            )

        checkout_id = await self._checkouts.create(
            {
                "account_id": account.id,
                "user_id": actor.id,
                "request_id": request.id if request else None,
                "reason": reason,
                "secret_version": account.secret_version,
                "checked_out_at": now,
                "expires_at": now + timedelta(minutes=duration),
                "status": CheckoutStatus.ACTIVE,
            }
        )
        if request is not None:
            multi_use = RequestPolicyDTO.from_snapshot(request.policy).approval_multi_use
            consumed: dict = {"uses": request.uses + 1}
            if not multi_use:
                consumed["status"] = RequestStatus.USED
            await self._requests.update(request.id, consumed)
        await self._audit.record(
            actor,
            "checkout.create",
            object_type="checkout",
            object_id=checkout_id,
            safe_id=account.safe_id,
            details={
                "account_id": str(account.id),
                "request_id": str(request.id) if request else None,
                "duration_minutes": duration,
            },
        )
        await self._checkouts.commit()
        return await self.get(checkout_id)

    async def reveal(self, actor: Actor, checkout_id: uuid.UUID) -> RevealedSecretDTO:
        co = await self.get(checkout_id)
        if co.user_id != actor.id:
            raise ForbiddenError("Only the holder of a check-out can reveal its secret")
        if co.status != CheckoutStatus.ACTIVE or co.expires_at <= utcnow():
            raise ConflictError("Check-out is no longer active")
        account = await self._accounts.get(co.account_id)
        # Membership can change mid check-out, and a session check-out (``use``) never
        # entitles its holder to see the secret.
        await self._accounts.authorise(actor, account, SafePermission.RETRIEVE)
        # The current version: if an admin replaced the secret mid check-out, the
        # holder needs the new one.
        value = await self._vault.read(
            owner_type=ACCOUNT_SECRET, owner_id=account.id, version=account.secret_version
        )
        await self._audit.record(
            actor,
            "secret.reveal",
            object_type="checkout",
            object_id=co.id,
            safe_id=account.safe_id,
            details={"account_id": str(account.id), "version": account.secret_version},
        )
        await self._checkouts.commit()
        return RevealedSecretDTO(
            checkout_id=co.id,
            username=account.username,
            secret_type=account.secret_type,
            value=value,
            expires_at=co.expires_at,
        )

    async def checkin(self, actor: Actor, checkout_id: uuid.UUID) -> CheckoutDTO:
        co = await self.get(checkout_id, lock=True)
        is_holder = co.user_id == actor.id
        if not is_holder and not actor.can(ACCESS_REVOKE):
            raise ForbiddenError("Only the holder or an administrator can close this check-out")
        if co.status != CheckoutStatus.ACTIVE:
            raise ConflictError(f"Check-out is already {co.status}")
        await self._checkouts.update(
            co.id,
            {
                "status": CheckoutStatus.RETURNED if is_holder else CheckoutStatus.REVOKED,
                "checked_in_at": utcnow(),
                "closed_by": actor.id,
            },
        )
        await self._audit.record(
            actor,
            "checkout.return" if is_holder else "checkout.revoke",
            object_type="checkout",
            object_id=co.id,
            safe_id=co.account.safe_id,
            details={"account_id": str(co.account_id)},
        )
        await self._rotation.after_use([co.account_id])
        await self._checkouts.commit()
        return await self.get(co.id)

    # ── Expiry ──

    async def sweep(self) -> dict[str, int] | None:
        """The scheduler's expiry pass: ``expire_overdue`` under a cluster-wide lock.

        None when another process holds the lock, so several schedulers do not
        double the work (the caller rolls back).
        """
        if not await self._checkouts.try_advisory_lock(EXPIRY_LOCK_KEY):
            return None
        return await self.expire_overdue()

    async def expire_overdue(self) -> dict[str, int]:
        """Close check-outs and requests whose time has passed. Safe to run concurrently."""
        checkouts = await self._expire_checkouts()
        expired_requests = await self._requests.expire_open(utcnow())
        safes = await self._accounts.safe_ids_for([acc for _, _, acc in expired_requests])
        for req_id, requester_id, account_id in expired_requests:
            await self._audit.record(
                SYSTEM_ACTOR,
                "request.expire",
                object_type="request",
                object_id=req_id,
                safe_id=safes.get(account_id),
            )
            await self._notify.notify(
                [requester_id],
                kind="request.expired",
                title="Your access request expired",
                object_type="request",
                object_id=req_id,
            )
        await self._checkouts.commit()
        return {"checkouts": checkouts, "requests": len(expired_requests)}

    async def _expire_checkouts(self, *, account_id: uuid.UUID | None = None) -> int:
        expired = await self._checkouts.expire_overdue(utcnow(), account_id=account_id)
        safes = await self._accounts.safe_ids_for([acc for _, acc in expired])
        for co_id, acc_id in expired:
            await self._audit.record(
                SYSTEM_ACTOR,
                "checkout.expire",
                object_type="checkout",
                object_id=co_id,
                safe_id=safes.get(acc_id),
                details={"account_id": str(acc_id)},
            )
        await self._rotation.after_use([acc for _, acc in expired])
        return len(expired)
