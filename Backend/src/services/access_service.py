"""Access requests, approvals, check-out, reveal and check-in.

Rules:
- An account that requires approval is checked out only against an approved
  request of the same person; the approver can never be the requester.
- An exclusive account has at most one active check-out at a time. The account
  row lock serialises competing check-outs, so two people cannot both win.
- Every decision, check-out, reveal and check-in is audited in the same
  transaction as the change it records.
"""

from __future__ import annotations

import uuid
from datetime import timedelta

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.contracts.schemas.access import (
    AccountBrief,
    CheckoutCreate,
    CheckoutOut,
    RequestCreate,
    RequestOut,
    RevealedSecret,
    UserBrief,
)
from src.core.config import Settings
from src.core.context import SYSTEM_ACTOR, Actor
from src.core.enums import CheckoutStatus, RequestStatus, Role
from src.errors.exceptions import ConflictError, ForbiddenError, NotFoundError
from src.models import AccessRequest, Account, Checkout, utcnow
from src.services import audit_service, vault_service
from src.services.inventory_service import ACCOUNT_SECRET, get_account

OPEN_REQUEST = (RequestStatus.PENDING, RequestStatus.APPROVED)

# ── Output mapping ──


def _account_brief(account: Account) -> AccountBrief:
    return AccountBrief(
        id=account.id,
        username=account.username,
        target_id=account.target_id,
        target_name=account.target.name,
        target_address=account.target.address,
    )


def request_out(req: AccessRequest) -> RequestOut:
    return RequestOut(
        id=req.id,
        account=_account_brief(req.account),
        requester=UserBrief.model_validate(req.requester),
        reason=req.reason,
        ticket_ref=req.ticket_ref,
        duration_minutes=req.duration_minutes,
        status=RequestStatus(req.status),
        decided_by=UserBrief.model_validate(req.decider) if req.decider else None,
        decided_at=req.decided_at,
        decision_note=req.decision_note,
        expires_at=req.expires_at,
        created_at=req.created_at,
    )


def checkout_out(co: Checkout) -> CheckoutOut:
    return CheckoutOut(
        id=co.id,
        account=_account_brief(co.account),
        user=UserBrief.model_validate(co.user),
        request_id=co.request_id,
        reason=co.reason,
        status=CheckoutStatus(co.status),
        checked_out_at=co.checked_out_at,
        expires_at=co.expires_at,
        checked_in_at=co.checked_in_at,
    )


# ── Requests ──


async def _get_request(
    session: AsyncSession, request_id: uuid.UUID, *, lock: bool = False
) -> AccessRequest:
    stmt = (
        select(AccessRequest)
        .where(AccessRequest.id == request_id)
        .execution_options(populate_existing=True)
    )
    if lock:
        stmt = stmt.with_for_update(of=AccessRequest)
    req = (await session.execute(stmt)).scalar_one_or_none()
    if req is None:
        raise NotFoundError("Request not found")
    return req


async def list_requests(
    session: AsyncSession,
    actor: Actor,
    *,
    page: int,
    page_size: int,
    status: RequestStatus | None = None,
    mine: bool = False,
) -> tuple[list[RequestOut], int]:
    conditions = []
    # Plain users and auditors only ever see their own requests.
    if mine or not actor.has_role(Role.ADMIN, Role.APPROVER):
        conditions.append(AccessRequest.requester_id == actor.id)
    if status:
        conditions.append(AccessRequest.status == status)
    total = (
        await session.execute(select(func.count()).select_from(AccessRequest).where(*conditions))
    ).scalar_one()
    rows = (
        (
            await session.execute(
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
    return [request_out(r) for r in rows], total


async def create_request(
    session: AsyncSession, settings: Settings, actor: Actor, body: RequestCreate
) -> RequestOut:
    account = await get_account(session, body.account_id)
    if not account.requires_approval:
        raise ConflictError("This account does not need approval; check it out directly")
    if body.duration_minutes > account.max_checkout_minutes:
        raise ConflictError(
            f"Duration exceeds this account's limit of {account.max_checkout_minutes} minutes"
        )
    req = AccessRequest(
        account_id=account.id,
        requester_id=actor.id,
        reason=body.reason,
        ticket_ref=body.ticket_ref,
        duration_minutes=body.duration_minutes,
        status=RequestStatus.PENDING,
        expires_at=utcnow() + timedelta(minutes=settings.request_window_minutes),
    )
    session.add(req)
    try:
        await session.flush()
    except IntegrityError as exc:
        raise ConflictError("You already have an open request for this account") from exc
    await audit_service.record(
        session,
        actor,
        "request.create",
        object_type="request",
        object_id=req.id,
        details={
            "account_id": str(account.id),
            "duration_minutes": body.duration_minutes,
            "ticket_ref": body.ticket_ref,
        },
    )
    await session.commit()
    return request_out(await _get_request(session, req.id))


async def decide_request(
    session: AsyncSession,
    settings: Settings,
    actor: Actor,
    request_id: uuid.UUID,
    *,
    approve: bool,
    note: str | None,
) -> RequestOut:
    req = await _get_request(session, request_id, lock=True)
    if req.requester_id == actor.id:
        raise ForbiddenError("You cannot decide your own request")
    if req.status != RequestStatus.PENDING:
        raise ConflictError(f"Request is already {req.status}")
    now = utcnow()
    if req.expires_at <= now:
        req.status = RequestStatus.EXPIRED
        await audit_service.record(
            session, SYSTEM_ACTOR, "request.expire", object_type="request", object_id=req.id
        )
        await session.commit()
        raise ConflictError("Request expired before a decision was made")

    req.status = RequestStatus.APPROVED if approve else RequestStatus.DENIED
    req.decided_by = actor.id
    req.decided_at = now
    req.decision_note = note
    if approve:
        # The approval is usable for one window from now.
        req.expires_at = now + timedelta(minutes=settings.request_window_minutes)
    await audit_service.record(
        session,
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
    await session.commit()
    return request_out(await _get_request(session, req.id))


async def cancel_request(session: AsyncSession, actor: Actor, request_id: uuid.UUID) -> RequestOut:
    req = await _get_request(session, request_id, lock=True)
    if req.requester_id != actor.id:
        raise ForbiddenError("Only the requester can cancel a request")
    if req.status not in OPEN_REQUEST:
        raise ConflictError(f"Request is already {req.status}")
    req.status = RequestStatus.CANCELLED
    await audit_service.record(
        session, actor, "request.cancel", object_type="request", object_id=req.id
    )
    await session.commit()
    return request_out(req)


# ── Check-outs ──


async def _get_checkout(
    session: AsyncSession, checkout_id: uuid.UUID, *, lock: bool = False
) -> Checkout:
    stmt = (
        select(Checkout).where(Checkout.id == checkout_id).execution_options(populate_existing=True)
    )
    if lock:
        stmt = stmt.with_for_update(of=Checkout)
    co = (await session.execute(stmt)).unique().scalar_one_or_none()
    if co is None:
        raise NotFoundError("Check-out not found")
    return co


async def list_checkouts(
    session: AsyncSession,
    actor: Actor,
    *,
    page: int,
    page_size: int,
    status: CheckoutStatus | None = None,
    mine: bool = False,
) -> tuple[list[CheckoutOut], int]:
    conditions = []
    if mine or not actor.has_role(Role.ADMIN, Role.AUDITOR):
        conditions.append(Checkout.user_id == actor.id)
    if status:
        conditions.append(Checkout.status == status)
    total = (
        await session.execute(select(func.count()).select_from(Checkout).where(*conditions))
    ).scalar_one()
    rows = (
        (
            await session.execute(
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
    return [checkout_out(c) for c in rows], total


async def checkout(session: AsyncSession, actor: Actor, body: CheckoutCreate) -> CheckoutOut:
    account = await get_account(session, body.account_id, lock=True)
    if account.secret_version == 0:
        raise ConflictError("No secret is stored for this account yet")
    now = utcnow()

    request: AccessRequest | None = None
    if account.requires_approval:
        if body.request_id is None:
            raise ForbiddenError("This account requires an approved request")
        request = await _get_request(session, body.request_id, lock=True)
        if request.requester_id != actor.id or request.account_id != account.id:
            raise ForbiddenError("That request is not yours for this account")
        if request.status != RequestStatus.APPROVED:
            raise ConflictError(f"Request is {request.status}, not approved")
        if request.expires_at <= now:
            request.status = RequestStatus.EXPIRED
            await session.commit()
            raise ConflictError("The approval has expired; submit a new request")
        duration = request.duration_minutes
        reason = request.reason
    else:
        duration = body.duration_minutes or min(60, account.max_checkout_minutes)
        if duration > account.max_checkout_minutes:
            raise ConflictError(
                f"Duration exceeds this account's limit of {account.max_checkout_minutes} minutes"
            )
        if not body.reason or len(body.reason.strip()) < 3:
            raise ConflictError("A reason is required to check out a credential")
        reason = body.reason.strip()

    # Close check-outs whose time ran out but the sweeper has not reached yet.
    await _expire_checkouts(session, account_id=account.id)
    holders = (
        (
            await session.execute(
                select(Checkout).where(
                    Checkout.account_id == account.id, Checkout.status == CheckoutStatus.ACTIVE
                )
            )
        )
        .unique()
        .scalars()
        .all()
    )
    if any(h.user_id == actor.id for h in holders):
        raise ConflictError("You already have this account checked out")
    if account.exclusive_checkout and holders:
        raise ConflictError(
            "Account is checked out by someone else",
            {"held_by": holders[0].user.username, "until": holders[0].expires_at.isoformat()},
        )

    co = Checkout(
        account_id=account.id,
        user_id=actor.id,
        request_id=request.id if request else None,
        reason=reason,
        secret_version=account.secret_version,
        checked_out_at=now,
        expires_at=now + timedelta(minutes=duration),
        status=CheckoutStatus.ACTIVE,
    )
    session.add(co)
    if request is not None:
        request.status = RequestStatus.USED
    await session.flush()
    await audit_service.record(
        session,
        actor,
        "checkout.create",
        object_type="checkout",
        object_id=co.id,
        details={
            "account_id": str(account.id),
            "request_id": str(request.id) if request else None,
            "duration_minutes": duration,
        },
    )
    await session.commit()
    return checkout_out(await _get_checkout(session, co.id))


async def reveal(session: AsyncSession, actor: Actor, checkout_id: uuid.UUID) -> RevealedSecret:
    co = await _get_checkout(session, checkout_id)
    if co.user_id != actor.id:
        raise ForbiddenError("Only the holder of a check-out can reveal its secret")
    if co.status != CheckoutStatus.ACTIVE or co.expires_at <= utcnow():
        raise ConflictError("Check-out is no longer active")
    account = co.account
    # The current version: if an admin replaced the secret mid check-out, the
    # holder needs the new one.
    value = await vault_service.read(
        session, owner_type=ACCOUNT_SECRET, owner_id=account.id, version=account.secret_version
    )
    await audit_service.record(
        session,
        actor,
        "secret.reveal",
        object_type="checkout",
        object_id=co.id,
        details={"account_id": str(account.id), "version": account.secret_version},
    )
    await session.commit()
    return RevealedSecret(
        checkout_id=co.id,
        username=account.username,
        secret_type=account.secret_type,
        value=value,
        expires_at=co.expires_at,
    )


async def checkin(session: AsyncSession, actor: Actor, checkout_id: uuid.UUID) -> CheckoutOut:
    co = await _get_checkout(session, checkout_id, lock=True)
    is_holder = co.user_id == actor.id
    if not is_holder and not actor.is_admin:
        raise ForbiddenError("Only the holder or an administrator can close this check-out")
    if co.status != CheckoutStatus.ACTIVE:
        raise ConflictError(f"Check-out is already {co.status}")
    co.status = CheckoutStatus.RETURNED if is_holder else CheckoutStatus.REVOKED
    co.checked_in_at = utcnow()
    co.closed_by = actor.id
    await audit_service.record(
        session,
        actor,
        "checkout.return" if is_holder else "checkout.revoke",
        object_type="checkout",
        object_id=co.id,
        details={"account_id": str(co.account_id)},
    )
    await session.commit()
    return checkout_out(co)


# ── Expiry ──


async def _expire_checkouts(session: AsyncSession, *, account_id: uuid.UUID | None = None) -> int:
    now = utcnow()
    stmt = (
        update(Checkout)
        .where(Checkout.status == CheckoutStatus.ACTIVE, Checkout.expires_at <= now)
        .values(status=CheckoutStatus.EXPIRED, checked_in_at=now)
        .returning(Checkout.id, Checkout.account_id)
    )
    if account_id is not None:
        stmt = stmt.where(Checkout.account_id == account_id)
    expired = (await session.execute(stmt)).all()
    for co_id, acc_id in expired:
        await audit_service.record(
            session,
            SYSTEM_ACTOR,
            "checkout.expire",
            object_type="checkout",
            object_id=co_id,
            details={"account_id": str(acc_id)},
        )
    return len(expired)


async def expire_overdue(session: AsyncSession) -> dict[str, int]:
    """Close check-outs and requests whose time has passed. Safe to run concurrently."""
    checkouts = await _expire_checkouts(session)
    expired_requests = (
        (
            await session.execute(
                update(AccessRequest)
                .where(AccessRequest.status.in_(OPEN_REQUEST), AccessRequest.expires_at <= utcnow())
                .values(status=RequestStatus.EXPIRED)
                .returning(AccessRequest.id)
            )
        )
        .scalars()
        .all()
    )
    for req_id in expired_requests:
        await audit_service.record(
            session, SYSTEM_ACTOR, "request.expire", object_type="request", object_id=req_id
        )
    await session.commit()
    return {"checkouts": checkouts, "requests": len(expired_requests)}
