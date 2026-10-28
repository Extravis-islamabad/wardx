"""Access requests and the approval workflow (docs/phase1/SAFES_AND_APPROVALS.md, (b)).

Rules:
- Only an account whose safe requires approval takes requests. Requesting needs
  'retrieve' or 'use' on the safe (404 when the requester cannot list it). The ticket
  is validated per the safe's ticket mode and pattern; the duration stays within the
  account's limit. One open (pending or approved) request per person per account.
- A request runs on a snapshot of the safe's policy taken when it is made, starting at
  level 1. Each level has a deadline of ``level_timeout_hours``.
- Deciding: see ApproverService for who may decide. Any deny ends the request. When a
  level reaches its required approvals the request moves to the next level; after the
  last it is approved with ``valid_until = approved_at + approval_window_minutes``
  (stored in ``expires_at``).
- Every decision is audited with its level; notifications go to the level's approvers
  (on create and advance) and to the requester (on advance, approve, deny, expiry).
"""

from __future__ import annotations

import uuid
from datetime import timedelta

from src.contracts.dto.access.access_request_dto import AccessRequestDTO, AccessRequestFilterDTO
from src.contracts.dto.safes.approval_policy_dto import RequestPolicyDTO
from src.core.context import SYSTEM_ACTOR, Actor
from src.core.enums import RequestStatus, SafePermission
from src.core.permissions import ACCESS_VIEW_ALL
from src.errors.exceptions import ConflictError, ForbiddenError, NotFoundError
from src.models import utcnow
from src.repositories.access.access_request_repository import (
    OPEN_REQUEST,
    AccessRequestRepository,
)
from src.repositories.inventory.account_repository import AccountRepository
from src.services.access.approver_service import ApproverService
from src.services.access.ticket_validator import TicketValidator
from src.services.audit.audit_service import AuditService
from src.services.notify.notification_service import NotificationService
from src.services.safes.approval_policy_service import ApprovalPolicyService
from src.services.safes.safe_access_service import SafeAccessService


def _label(req: AccessRequestDTO) -> str:
    return f"{req.account.username}@{req.account.target_name}"


class AccessRequestService:
    def __init__(
        self,
        requests: AccessRequestRepository,
        accounts: AccountRepository,
        audit: AuditService,
        access: SafeAccessService,
        policies: ApprovalPolicyService,
        approvers: ApproverService,
        notifications: NotificationService,
        tickets: TicketValidator,
    ) -> None:
        self._requests = requests
        self._accounts = accounts
        self._audit = audit
        self._access = access
        self._policies = policies
        self._approvers = approvers
        self._notify = notifications
        self._tickets = tickets

    async def list(
        self,
        actor: Actor,
        *,
        page: int,
        page_size: int,
        status: str | None = None,
        mine: bool = False,
        queue: bool = False,
    ) -> tuple[list[AccessRequestDTO], int]:
        if queue:
            ready = [r for r in await self.queue(actor) if not status or r.status == status]
            start = (page - 1) * page_size
            return ready[start : start + page_size], len(ready)
        if mine:
            filters = AccessRequestFilterDTO(requester_id=actor.id, status=status)
        elif actor.can(ACCESS_VIEW_ALL):
            filters = AccessRequestFilterDTO(status=status)
        else:
            # Requests on accounts the actor can list, and their own.
            filters = AccessRequestFilterDTO(
                status=status,
                safe_ids=await self._access.listable_safe_ids(actor),
                include_requester_id=actor.id,
            )
        return await self._requests.list(filters, page=page, page_size=page_size)

    async def queue(self, actor: Actor) -> list[AccessRequestDTO]:
        """Pending requests the actor can decide at their current level, oldest first."""
        return [
            r
            for r in await self._requests.pending()
            if await self._approvers.why_not(actor, r) is None
        ]

    async def get(self, request_id: uuid.UUID, *, lock: bool = False) -> AccessRequestDTO:
        req = await self._requests.get(request_id, lock=lock)
        if req is None:
            raise NotFoundError("Request not found")
        return req

    async def usable_approval(self, actor: Actor, account_id: uuid.UUID) -> AccessRequestDTO | None:
        """The actor's latest approved request for the account still in its window."""
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
        await self._access.require(
            actor, account.safe_id, SafePermission.RETRIEVE, SafePermission.USE
        )
        policy = await self._policies.policy(account.safe_id)
        if not policy.approval_required:
            raise ConflictError("This account does not need approval; check it out directly")
        if not policy.levels:
            raise ConflictError("This safe requires approval but has no approval levels")
        if duration_minutes > account.max_checkout_minutes:
            raise ConflictError(
                f"Duration exceeds this account's limit of {account.max_checkout_minutes} minutes"
            )
        ticket = await self._tickets.validate(policy, ticket_ref)
        now = utcnow()
        request_id = await self._requests.create(
            {
                "account_id": account.id,
                "requester_id": actor.id,
                "reason": reason,
                "ticket_ref": ticket,
                "duration_minutes": duration_minutes,
                "status": RequestStatus.PENDING,
                "policy": policy.snapshot(),
                "current_level": 1,
                "level_started_at": now,
                "expires_at": now + timedelta(hours=policy.level_timeout_hours),
            }
        )
        await self._audit.record(
            actor,
            "request.create",
            object_type="request",
            object_id=request_id,
            details={
                "account_id": str(account.id),
                "safe_id": str(account.safe_id),
                "duration_minutes": duration_minutes,
                "ticket_ref": ticket,
                "levels": len(policy.levels),
            },
        )
        req = await self.get(request_id)
        await self._notify.notify(
            await self._approvers.recipients(req),
            kind="request.pending",
            title=f"{actor.username} requests {_label(req)}",
            body=f"Level 1 of {len(policy.levels)}. Reason: {reason}",
            object_type="request",
            object_id=request_id,
        )
        await self._requests.commit()
        return req

    async def _expire(self, req: AccessRequestDTO) -> None:
        await self._requests.update(req.id, {"status": RequestStatus.EXPIRED})
        await self._audit.record(
            SYSTEM_ACTOR,
            "request.expire",
            object_type="request",
            object_id=req.id,
            details={"level": req.current_level},
        )
        await self._notify.notify(
            [req.requester_id],
            kind="request.expired",
            title=f"Your request for {_label(req)} expired",
            object_type="request",
            object_id=req.id,
        )
        await self._requests.commit()

    async def decide(
        self, actor: Actor, request_id: uuid.UUID, *, approve: bool, note: str | None
    ) -> AccessRequestDTO:
        req = await self.get(request_id, lock=True)
        if req.status != RequestStatus.PENDING:
            raise ConflictError(f"Request is already {req.status}")
        now = utcnow()
        if req.expires_at <= now:
            await self._expire(req)
            raise ConflictError("Request expired before a decision was made")
        refusal = await self._approvers.why_not(actor, req)
        if refusal:
            raise ForbiddenError(refusal)

        policy = RequestPolicyDTO.from_snapshot(req.policy)
        level = policy.level(req.current_level)
        await self._requests.add_decision(
            {
                "request_id": req.id,
                "level": req.current_level,
                "approver_id": actor.id,
                "approve": approve,
                "note": note,
                "decided_at": now,
            }
        )
        approvals = 1 + sum(d.approve for d in req.decisions if d.level == req.current_level)
        details = {
            "account_id": str(req.account_id),
            "requester_id": str(req.requester_id),
            "level": req.current_level,
            "note": note,
        }
        changes: dict = {"decided_by": actor.id, "decided_at": now, "decision_note": note}
        notice = None
        if not approve:
            changes["status"] = RequestStatus.DENIED
            notice = ("request.denied", f"Your request for {_label(req)} was denied")
        elif approvals < level.required_approvals:
            details["approvals"] = f"{approvals} of {level.required_approvals}"
        elif req.current_level < policy.last_level:
            changes.update(
                current_level=req.current_level + 1,
                level_started_at=now,
                expires_at=now + timedelta(hours=policy.level_timeout_hours),
            )
            details["advanced_to"] = req.current_level + 1
            notice = (
                "request.advanced",
                f"Your request for {_label(req)} passed level {req.current_level}",
            )
        else:
            changes.update(
                status=RequestStatus.APPROVED,
                approved_at=now,
                expires_at=now + timedelta(minutes=policy.approval_window_minutes),
            )
            details["final"] = True
            notice = ("request.approved", f"Your request for {_label(req)} was approved")
        await self._requests.update(req.id, changes)
        await self._audit.record(
            actor,
            "request.approve" if approve else "request.deny",
            object_type="request",
            object_id=req.id,
            details=details,
        )
        updated = await self.get(req.id)
        if notice:
            await self._notify.notify(
                [req.requester_id],
                kind=notice[0],
                title=notice[1],
                body=note,
                object_type="request",
                object_id=req.id,
            )
        if "advanced_to" in details:
            await self._notify.notify(
                await self._approvers.recipients(updated),
                kind="request.pending",
                title=f"{req.requester.username} requests {_label(req)}",
                body=f"Level {updated.current_level} of {policy.last_level}. Reason: {req.reason}",
                object_type="request",
                object_id=req.id,
            )
        await self._requests.commit()
        return updated

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
