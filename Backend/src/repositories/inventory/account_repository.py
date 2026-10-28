"""Privileged accounts (inventory.accounts), each loaded with its target."""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError

from src.contracts.dto.inventory.account_dto import (
    AccountDTO,
    AccountFilterDTO,
    SafeBriefDTO,
    TargetBriefDTO,
)
from src.core.enums import CheckoutStatus
from src.errors.exceptions import ConflictError
from src.models import Account, Checkout, Target
from src.repositories.base import BaseRepository


def _to_dto(row: Account, active_checkouts: int = 0) -> AccountDTO:
    t = row.target
    return AccountDTO(
        id=row.id,
        target=TargetBriefDTO(
            id=t.id,
            name=t.name,
            address=t.address,
            platform=t.platform,
            protocol=t.protocol,
            port=t.port,
        ),
        safe=SafeBriefDTO(id=row.safe.id, name=row.safe.name),
        username=row.username,
        secret_type=row.secret_type,
        description=row.description,
        secret_version=row.secret_version,
        secret_updated_at=row.secret_updated_at,
        # The retired per-account flag is no longer read: approval is the safe's policy.
        requires_approval=row.safe.approval_required,
        exclusive_checkout=row.exclusive_checkout,
        max_checkout_minutes=row.max_checkout_minutes,
        rotation_interval_days=row.rotation_interval_days,
        rotate_after_checkin=row.rotate_after_checkin,
        password_length=row.password_length,
        last_rotated_at=row.last_rotated_at,
        last_rotation_status=row.last_rotation_status,
        created_at=row.created_at,
        active_checkouts=active_checkouts,
    )


class AccountRepository(BaseRepository):
    async def active_checkout_counts(
        self, account_ids: Sequence[uuid.UUID]
    ) -> dict[uuid.UUID, int]:
        if not account_ids:
            return {}
        rows = await self._session.execute(
            select(Checkout.account_id, func.count())
            .where(Checkout.account_id.in_(account_ids), Checkout.status == CheckoutStatus.ACTIVE)
            .group_by(Checkout.account_id)
        )
        return dict(rows.all())

    async def list(
        self, filters: AccountFilterDTO, *, page: int, page_size: int
    ) -> tuple[list[AccountDTO], int]:
        conditions = []
        if filters.target_id:
            conditions.append(Account.target_id == filters.target_id)
        if filters.safe_id:
            conditions.append(Account.safe_id == filters.safe_id)
        if filters.safe_ids is not None:
            conditions.append(Account.safe_id.in_(filters.safe_ids))
        if filters.search:
            like = f"%{filters.search.lower()}%"
            conditions.append(
                or_(
                    func.lower(Account.username).like(like),
                    func.lower(Target.name).like(like),
                    func.lower(Target.address).like(like),
                )
            )
        base = select(Account).join(Account.target).where(*conditions)
        total = await self._session.scalar(select(func.count()).select_from(base.subquery()))
        rows = list(
            await self._session.scalars(
                base.order_by(func.lower(Target.name), func.lower(Account.username))
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        )
        counts = await self.active_checkout_counts([a.id for a in rows])
        return [_to_dto(a, counts.get(a.id, 0)) for a in rows], total or 0

    async def get(self, account_id: uuid.UUID, *, lock: bool = False) -> AccountDTO | None:
        """The account with its active check-out count; ``lock`` holds the account row
        until the transaction ends, which serialises check-outs and secret writes."""
        # populate_existing: a just-created account in the identity map gets its target loaded.
        stmt = (
            select(Account)
            .where(Account.id == account_id)
            .execution_options(populate_existing=True)
        )
        if lock:
            # Lock only the account row, not the joined target.
            stmt = stmt.with_for_update(of=Account)
        row = (await self._session.execute(stmt)).scalar_one_or_none()
        if row is None:
            return None
        counts = await self.active_checkout_counts([row.id])
        return _to_dto(row, counts.get(row.id, 0))

    async def list_for_target(self, target_id: uuid.UUID) -> list[AccountDTO]:
        """Every account on a target (without active check-out counts)."""
        rows = await self._session.scalars(select(Account).where(Account.target_id == target_id))
        return [_to_dto(a) for a in rows]

    async def ids_for_target(self, target_id: uuid.UUID) -> list[uuid.UUID]:
        return list(
            await self._session.scalars(select(Account.id).where(Account.target_id == target_id))
        )

    async def create(self, values: dict[str, Any]) -> uuid.UUID:
        row = Account(**values)
        self._session.add(row)
        try:
            await self._session.flush()
        except IntegrityError as exc:
            raise ConflictError("This account already exists on the target") from exc
        return row.id

    async def update(self, account_id: uuid.UUID, changes: dict[str, Any]) -> None:
        row = await self._session.get(Account, account_id)
        for field, value in changes.items():
            setattr(row, field, value)
        await self._session.flush()

    async def delete(self, account_id: uuid.UUID) -> None:
        row = await self._session.get(Account, account_id)
        if row is not None:
            await self._session.delete(row)
            await self._session.flush()
