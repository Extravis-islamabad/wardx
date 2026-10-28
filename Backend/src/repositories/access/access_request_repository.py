"""Access requests (access.requests), each loaded with its account, requester and decider."""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import datetime
from typing import Any

from sqlalchemy import func, or_, select, update
from sqlalchemy.exc import IntegrityError

from src.contracts.dto.access.access_request_dto import (
    AccessRequestDTO,
    AccessRequestFilterDTO,
    RequestDecisionDTO,
)
from src.core.enums import RequestStatus
from src.errors.exceptions import ConflictError
from src.models import AccessRequest, Account, RequestDecision
from src.repositories.access.briefs import account_brief, user_brief
from src.repositories.base import BaseRepository

OPEN_REQUEST = (RequestStatus.PENDING, RequestStatus.APPROVED)


def _decision(row: RequestDecision) -> RequestDecisionDTO:
    return RequestDecisionDTO(
        level=row.level,
        approver=user_brief(row.approver),
        approve=row.approve,
        note=row.note,
        decided_at=row.decided_at,
    )


def _to_dto(row: AccessRequest, decisions: Sequence[RequestDecisionDTO] = ()) -> AccessRequestDTO:
    return AccessRequestDTO(
        id=row.id,
        account=account_brief(row.account),
        requester=user_brief(row.requester),
        reason=row.reason,
        ticket_ref=row.ticket_ref,
        duration_minutes=row.duration_minutes,
        status=row.status,
        decided_by=user_brief(row.decider) if row.decider else None,
        decided_at=row.decided_at,
        decision_note=row.decision_note,
        expires_at=row.expires_at,
        created_at=row.created_at,
        current_level=row.current_level,
        level_started_at=row.level_started_at,
        policy=row.policy,
        approved_at=row.approved_at,
        uses=row.uses,
        decisions=tuple(decisions),
    )


class AccessRequestRepository(BaseRepository):
    async def list(
        self, filters: AccessRequestFilterDTO, *, page: int, page_size: int
    ) -> tuple[list[AccessRequestDTO], int]:
        conditions = []
        if filters.requester_id is not None:
            conditions.append(AccessRequest.requester_id == filters.requester_id)
        if filters.status:
            conditions.append(AccessRequest.status == filters.status)
        if filters.safe_ids is not None:
            in_safes = AccessRequest.account_id.in_(
                select(Account.id).where(Account.safe_id.in_(filters.safe_ids))
            )
            if filters.include_requester_id is not None:
                in_safes = or_(in_safes, AccessRequest.requester_id == filters.include_requester_id)
            conditions.append(in_safes)
        total = (
            await self._session.execute(
                select(func.count()).select_from(AccessRequest).where(*conditions)
            )
        ).scalar_one()
        rows = (
            (
                await self._session.execute(
                    select(AccessRequest)
                    .where(*conditions)
                    .order_by(AccessRequest.created_at.desc())
                    .offset((page - 1) * page_size)
                    .limit(page_size)
                )
            )
            .unique()
            .scalars()
            .all()
        )
        decisions = await self.decisions_for([r.id for r in rows])
        return [_to_dto(r, decisions.get(r.id, ())) for r in rows], total

    async def pending(self) -> list[AccessRequestDTO]:
        """Every pending request, oldest first (for the approvals queue)."""
        rows = (
            (
                await self._session.execute(
                    select(AccessRequest)
                    .where(AccessRequest.status == RequestStatus.PENDING)
                    .order_by(AccessRequest.created_at)
                )
            )
            .unique()
            .scalars()
            .all()
        )
        decisions = await self.decisions_for([r.id for r in rows])
        return [_to_dto(r, decisions.get(r.id, ())) for r in rows]

    async def decisions_for(
        self, request_ids: Sequence[uuid.UUID]
    ) -> dict[uuid.UUID, list[RequestDecisionDTO]]:
        if not request_ids:
            return {}
        rows = await self._session.scalars(
            select(RequestDecision)
            .where(RequestDecision.request_id.in_(request_ids))
            .order_by(RequestDecision.decided_at)
        )
        out: dict[uuid.UUID, list[RequestDecisionDTO]] = {}
        for row in rows:
            out.setdefault(row.request_id, []).append(_decision(row))
        return out

    async def add_decision(self, values: dict[str, Any]) -> None:
        self._session.add(RequestDecision(**values))
        try:
            await self._session.flush()
        except IntegrityError as exc:
            raise ConflictError("You have already decided this request") from exc

    async def get(self, request_id: uuid.UUID, *, lock: bool = False) -> AccessRequestDTO | None:
        """The request; ``lock`` holds its row until the transaction ends."""
        stmt = (
            select(AccessRequest)
            .where(AccessRequest.id == request_id)
            .execution_options(populate_existing=True)
        )
        if lock:
            stmt = stmt.with_for_update(of=AccessRequest)
        row = (await self._session.execute(stmt)).scalar_one_or_none()
        if row is None:
            return None
        return _to_dto(row, (await self.decisions_for([row.id])).get(row.id, ()))

    async def latest_approved(
        self, account_id: uuid.UUID, requester_id: uuid.UUID, now: datetime
    ) -> AccessRequestDTO | None:
        """The requester's most recently approved, unexpired request for the account."""
        row = (
            (
                await self._session.execute(
                    select(AccessRequest)
                    .where(
                        AccessRequest.account_id == account_id,
                        AccessRequest.requester_id == requester_id,
                        AccessRequest.status == RequestStatus.APPROVED,
                        AccessRequest.expires_at > now,
                    )
                    .order_by(AccessRequest.decided_at.desc())
                    .limit(1)
                )
            )
            .unique()
            .scalar_one_or_none()
        )
        return _to_dto(row) if row else None

    async def create(self, values: dict[str, Any]) -> uuid.UUID:
        row = AccessRequest(**values)
        self._session.add(row)
        try:
            await self._session.flush()
        except IntegrityError as exc:
            raise ConflictError("You already have an open request for this account") from exc
        return row.id

    async def update(self, request_id: uuid.UUID, changes: dict[str, Any]) -> None:
        row = await self._session.get(AccessRequest, request_id)
        for field, value in changes.items():
            setattr(row, field, value)
        await self._session.flush()

    async def expire_open(self, now: datetime) -> list[tuple[uuid.UUID, uuid.UUID, uuid.UUID]]:
        """Expire pending requests whose level timed out and approved ones past their
        window: ``(request id, requester id, account id)`` of each."""
        return [
            (rid, requester, account)
            for rid, requester, account in (
                await self._session.execute(
                    update(AccessRequest)
                    .where(AccessRequest.status.in_(OPEN_REQUEST), AccessRequest.expires_at <= now)
                    .values(status=RequestStatus.EXPIRED)
                    .returning(
                        AccessRequest.id, AccessRequest.requester_id, AccessRequest.account_id
                    )
                )
            ).all()
        ]
