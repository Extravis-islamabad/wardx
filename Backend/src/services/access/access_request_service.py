"""Access requests and their approval.

Rules:
- Only an account that requires approval takes requests, and a request never
  asks for longer than the account's check-out limit.
- One open (pending or approved) request per person per account.
- The approver can never be the requester. A request not decided within the
  request window expires; an approval is usable for one window from approval.
- Every decision is audited in the same transaction as the change it records.
"""

from __future__ import annotations

import uuid
from datetime import timedelta

from src.contracts.dto.access.access_request_dto import AccessRequestDTO, AccessRequestFilterDTO
from src.core.config import Settings
from src.core.context import SYSTEM_ACTOR, Actor
from src.core.enums import RequestStatus
from src.core.permissions import ACCESS_APPROVE
from src.errors.exceptions import ConflictError, ForbiddenError, NotFoundError
from src.models import utcnow
from src.repositories.access.access_request_repository import (
    OPEN_REQUEST,
    AccessRequestRepository,
)
from src.repositories.inventory.account_repository import AccountRepository
from src.services.audit.audit_service import AuditService


class AccessRequestService:
    def __init__(
        self,
        requests: AccessRequestRepository,
        accounts: AccountRepository,
        audit: AuditService,
        settings: Settings,
    ) -> None:
        self._requests = requests
        self._accounts = accounts
        self._audit = audit
        self._settings = settings

    async def list(
        self,
        actor: Actor,
        *,
        page: int,
        page_size: int,
        status: str | None = None,
        mine: bool = False,
    ) -> tuple[list[AccessRequestDTO], int]:
        # Without ACCESS_APPROVE (plain users, auditors) people only see their own requests.
        own = mine or not actor.can(ACCESS_APPROVE)
        return await self._requests.list(
            AccessRequestFilterDTO(requester_id=actor.id if own else None, status=status),
            page=page,
            page_size=page_size,
        )

    async def get(self, request_id: uuid.UUID, *, lock: bool = False) -> AccessRequestDTO:
        req = await self._requests.get(request_id, lock=lock)
        if req is None:
            raise NotFoundError("Request not found")
        return req

    async def usable_approval(self, actor: Actor, account_id: uuid.UUID) -> AccessRequestDTO | None:
        """The actor's latest approved, unexpired request for the account, if any."""
        return await self._requests.latest_approved(account_id, actor.id, utcnow())

    async def create(
        self,
        actor: Actor,
        *,
        account_id: uuid.UUID,
        reason: str,
        ticket_ref: str | None,
        duration_minutes: int,
    ) -> AccessRequestDTO:
        account = await self._accounts.get(account_id)
        if account is None:
            raise NotFoundError("Account not found")
        if not account.requires_approval:
            raise ConflictError("This account does not need approval; check it out directly")
        if duration_minutes > account.max_checkout_minutes:
            raise ConflictError(
                f"Duration exceeds this account's limit of {account.max_checkout_minutes} minutes"
            )
        request_id = await self._requests.create(
            {
                "account_id": account.id,
                "requester_id": actor.id,
                "reason": reason,
                "ticket_ref": ticket_ref,
                "duration_minutes": duration_minutes,
                "status": RequestStatus.PENDING,
                "expires_at": utcnow() + timedelta(minutes=self._settings.request_window_minutes),
            }
        )
        await self._audit.record(
            actor,
            "request.create",
            object_type="request",
            object_id=request_id,
            details={
                "account_id": str(account.id),
                "duration_minutes": duration_minutes,
                "ticket_ref": ticket_ref,
            },
        )
        await self._requests.commit()
        return await self.get(request_id)

    async def decide(
        self, actor: Actor, request_id: uuid.UUID, *, approve: bool, note: str | None
    ) -> AccessRequestDTO:
        req = await self.get(request_id, lock=True)
        if req.requester_id == actor.id:
            raise ForbiddenError("You cannot decide your own request")
        if req.status != RequestStatus.PENDING:
            raise ConflictError(f"Request is already {req.status}")
        now = utcnow()
        if req.expires_at <= now:
            await self._requests.update(req.id, {"status": RequestStatus.EXPIRED})
            await self._audit.record(
                SYSTEM_ACTOR, "request.expire", object_type="request", object_id=req.id
            )
            await self._requests.commit()
            raise ConflictError("Request expired before a decision was made")

        changes: dict = {
            "status": RequestStatus.APPROVED if approve else RequestStatus.DENIED,
            "decided_by": actor.id,
            "decided_at": now,
            "decision_note": note,
        }
        if approve:
            # The approval is usable for one window from now.
            changes["expires_at"] = now + timedelta(minutes=self._settings.request_window_minutes)
        await self._requests.update(req.id, changes)
        await self._audit.record(
            actor,
            "request.approve" if approve else "request.deny",
            object_type="request",
            object_id=req.id,
            details={
                "account_id": str(req.account_id),
                "requester_id": str(req.requester_id),
                "note": note,
            },
        )
        await self._requests.commit()
        return await self.get(req.id)

    async def cancel(self, actor: Actor, request_id: uuid.UUID) -> AccessRequestDTO:
        req = await self.get(request_id, lock=True)
        if req.requester_id != actor.id:
            raise ForbiddenError("Only the requester can cancel a request")
        if req.status not in OPEN_REQUEST:
            raise ConflictError(f"Request is already {req.status}")
        await self._requests.update(req.id, {"status": RequestStatus.CANCELLED})
        await self._audit.record(actor, "request.cancel", object_type="request", object_id=req.id)
        await self._requests.commit()
        return await self.get(req.id)
