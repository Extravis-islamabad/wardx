"""Check-outs (access.checkouts), each loaded with its account and holder."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import func, select, update

from src.contracts.dto.access.checkout_dto import CheckoutDTO, CheckoutFilterDTO
from src.core.enums import CheckoutStatus
from src.models import Checkout
from src.repositories.access.briefs import account_brief, user_brief
from src.repositories.base import BaseRepository


def _to_dto(row: Checkout) -> CheckoutDTO:
    return CheckoutDTO(
        id=row.id,
        account=account_brief(row.account),
        user=user_brief(row.user),
        request_id=row.request_id,
        reason=row.reason,
        secret_version=row.secret_version,
        status=row.status,
        checked_out_at=row.checked_out_at,
        expires_at=row.expires_at,
        checked_in_at=row.checked_in_at,
    )


class CheckoutRepository(BaseRepository):
    async def list(
        self, filters: CheckoutFilterDTO, *, page: int, page_size: int
    ) -> tuple[list[CheckoutDTO], int]:
        conditions = []
        if filters.user_id is not None:
            conditions.append(Checkout.user_id == filters.user_id)
        if filters.status:
            conditions.append(Checkout.status == filters.status)
        total = (
            await self._session.execute(
                select(func.count()).select_from(Checkout).where(*conditions)
            )
        ).scalar_one()
        rows = (
            (
                await self._session.execute(
                    select(Checkout)
                    .where(*conditions)
                    .order_by(Checkout.checked_out_at.desc())
                    .offset((page - 1) * page_size)
                    .limit(page_size)
                )
            )
            .unique()
            .scalars()
            .all()
        )
        return [_to_dto(c) for c in rows], total

    async def get(self, checkout_id: uuid.UUID, *, lock: bool = False) -> CheckoutDTO | None:
        """The check-out; ``lock`` holds its row until the transaction ends."""
        stmt = (
            select(Checkout)
            .where(Checkout.id == checkout_id)
            .execution_options(populate_existing=True)
        )
        if lock:
            stmt = stmt.with_for_update(of=Checkout)
        row = (await self._session.execute(stmt)).unique().scalar_one_or_none()
        return _to_dto(row) if row else None

    async def active_for_account(self, account_id: uuid.UUID) -> list[CheckoutDTO]:
        rows = (
            (
                await self._session.execute(
                    select(Checkout).where(
                        Checkout.account_id == account_id,
                        Checkout.status == CheckoutStatus.ACTIVE,
                    )
                )
            )
            .unique()
            .scalars()
            .all()
        )
        return [_to_dto(c) for c in rows]

    async def create(self, values: dict[str, Any]) -> uuid.UUID:
        row = Checkout(**values)
        self._session.add(row)
        await self._session.flush()
        return row.id

    async def update(self, checkout_id: uuid.UUID, changes: dict[str, Any]) -> None:
        row = await self._session.get(Checkout, checkout_id)
        for field, value in changes.items():
            setattr(row, field, value)
        await self._session.flush()

    async def expire_overdue(
        self, now: datetime, *, account_id: uuid.UUID | None = None
    ) -> list[tuple[uuid.UUID, uuid.UUID]]:
        """Mark active check-outs past ``expires_at`` expired; their (id, account_id)."""
        stmt = (
            update(Checkout)
            .where(Checkout.status == CheckoutStatus.ACTIVE, Checkout.expires_at <= now)
            .values(status=CheckoutStatus.EXPIRED, checked_in_at=now)
            .returning(Checkout.id, Checkout.account_id)
        )
        if account_id is not None:
            stmt = stmt.where(Checkout.account_id == account_id)
        return [(co_id, acc_id) for co_id, acc_id in (await self._session.execute(stmt)).all()]
