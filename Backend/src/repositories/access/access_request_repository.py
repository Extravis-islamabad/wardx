"""Access requests (access.requests), each loaded with its account, requester and decider."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError

from src.contracts.dto.access.access_request_dto import AccessRequestDTO, AccessRequestFilterDTO
from src.core.enums import RequestStatus
from src.errors.exceptions import ConflictError
from src.models import AccessRequest
from src.repositories.access.briefs import account_brief, user_brief
from src.repositories.base import BaseRepository

OPEN_REQUEST = (RequestStatus.PENDING, RequestStatus.APPROVED)


def _to_dto(row: AccessRequest) -> AccessRequestDTO:
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
        return [_to_dto(r) for r in rows], total

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

    async def expire_open(self, now: datetime) -> list[uuid.UUID]:
        """Mark pending and approved requests past ``expires_at`` expired; their ids."""
        return list(
            (
                await self._session.execute(
                    update(AccessRequest)
                    .where(AccessRequest.status.in_(OPEN_REQUEST), AccessRequest.expires_at <= now)
                    .values(status=RequestStatus.EXPIRED)
                    .returning(AccessRequest.id)
                )
            )
            .scalars()
            .all()
        )
