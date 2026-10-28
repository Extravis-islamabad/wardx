"""Headline counts across inventory and access, in one round trip."""

from __future__ import annotations

import uuid

from sqlalchemy import func, select

from src.contracts.dto.dashboard.dashboard_dto import DashboardSummaryDTO
from src.core.enums import CheckoutStatus, RequestStatus
from src.models import AccessRequest, Account, Checkout, Target
from src.repositories.base import BaseRepository


class DashboardRepository(BaseRepository):
    async def summary(self, user_id: uuid.UUID | None) -> DashboardSummaryDTO:
        active = Checkout.status == CheckoutStatus.ACTIVE
        open_request = AccessRequest.status.in_((RequestStatus.PENDING, RequestStatus.APPROVED))
        row = (
            await self._session.execute(
                select(
                    select(func.count()).select_from(Target).scalar_subquery(),
                    select(func.count()).select_from(Account).scalar_subquery(),
                    select(func.count())
                    .select_from(Account)
                    .where(Account.secret_version == 0)
                    .scalar_subquery(),
                    select(func.count()).select_from(Checkout).where(active).scalar_subquery(),
                    select(func.count())
                    .select_from(AccessRequest)
                    .where(AccessRequest.status == RequestStatus.PENDING)
                    .scalar_subquery(),
                    select(func.count())
                    .select_from(Checkout)
                    .where(active, Checkout.user_id == user_id)
                    .scalar_subquery(),
                    select(func.count())
                    .select_from(AccessRequest)
                    .where(open_request, AccessRequest.requester_id == user_id)
                    .scalar_subquery(),
                )
            )
        ).one()
        return DashboardSummaryDTO(
            targets=row[0],
            accounts=row[1],
            accounts_without_secret=row[2],
            active_checkouts=row[3],
            pending_requests=row[4],
            my_active_checkouts=row[5],
            my_open_requests=row[6],
        )
