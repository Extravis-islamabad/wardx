"""Headline counts for the home page."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.contracts.schemas.access import DashboardSummary
from src.core.context import Actor
from src.core.enums import CheckoutStatus, RequestStatus
from src.models import AccessRequest, Account, Checkout, Target


async def summary(session: AsyncSession, actor: Actor) -> DashboardSummary:
    active = Checkout.status == CheckoutStatus.ACTIVE
    open_request = AccessRequest.status.in_((RequestStatus.PENDING, RequestStatus.APPROVED))
    row = (
        await session.execute(
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
                .where(active, Checkout.user_id == actor.id)
                .scalar_subquery(),
                select(func.count())
                .select_from(AccessRequest)
                .where(open_request, AccessRequest.requester_id == actor.id)
                .scalar_subquery(),
            )
        )
    ).one()
    return DashboardSummary(
        targets=row[0],
        accounts=row[1],
        accounts_without_secret=row[2],
        active_checkouts=row[3],
        pending_requests=row[4],
        my_active_checkouts=row[5],
        my_open_requests=row[6],
    )
