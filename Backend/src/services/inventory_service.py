"""Targets and privileged accounts, including storing account secrets."""

from __future__ import annotations

import uuid

from sqlalchemy import delete, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.contracts.schemas.inventory import (
    AccountCreate,
    AccountOut,
    AccountUpdate,
    TargetBrief,
    TargetCreate,
    TargetUpdate,
)
from src.core.context import Actor
from src.core.enums import DEFAULT_PORTS, CheckoutStatus, Protocol
from src.errors.exceptions import ConflictError, NotFoundError
from src.models import Account, Checkout, Secret, Target, utcnow
from src.services import audit_service, vault_service

ACCOUNT_SECRET = "account"

# ── Targets ──


async def list_targets(
    session: AsyncSession,
    *,
    page: int,
    page_size: int,
    search: str | None = None,
    platform: str | None = None,
) -> tuple[list[Target], int]:
    conditions = []
    if search:
        like = f"%{search.lower()}%"
        conditions.append(
            or_(func.lower(Target.name).like(like), func.lower(Target.address).like(like))
        )
    if platform:
        conditions.append(Target.platform == platform)
    total = (
        await session.execute(select(func.count()).select_from(Target).where(*conditions))
    ).scalar_one()
    rows = (
        (
            await session.execute(
                select(Target)
                .where(*conditions)
                .order_by(func.lower(Target.name))
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        )
        .scalars()
        .all()
    )
    return list(rows), total


async def get_target(session: AsyncSession, target_id: uuid.UUID) -> Target:
    target = await session.get(Target, target_id)
    if target is None:
        raise NotFoundError("Target not found")
    return target


async def create_target(session: AsyncSession, actor: Actor, body: TargetCreate) -> Target:
    target = Target(
        **body.model_dump(exclude={"port"}),
        port=body.port or DEFAULT_PORTS[body.protocol],
    )
    session.add(target)
    try:
        await session.flush()
    except IntegrityError as exc:
        raise ConflictError("A target with this name already exists") from exc
    await audit_service.record(
        session,
        actor,
        "target.create",
        object_type="target",
        object_id=target.id,
        details={"name": target.name, "address": target.address, "platform": target.platform},
    )
    await session.commit()
    return target


async def update_target(
    session: AsyncSession, actor: Actor, target_id: uuid.UUID, body: TargetUpdate
) -> Target:
    target = await get_target(session, target_id)
    changes = body.model_dump(exclude_unset=True)
    if "protocol" in changes and "port" not in changes:
        changes["port"] = DEFAULT_PORTS[Protocol(changes["protocol"])]
    for field, value in changes.items():
        setattr(target, field, value)
    try:
        await session.flush()
    except IntegrityError as exc:
        raise ConflictError("A target with this name already exists") from exc
    await audit_service.record(
        session,
        actor,
        "target.update",
        object_type="target",
        object_id=target.id,
        details={
            k: str(v) if not isinstance(v, bool | int | list) else v for k, v in changes.items()
        },
    )
    await session.commit()
    return target


async def delete_target(session: AsyncSession, actor: Actor, target_id: uuid.UUID) -> None:
    target = await get_target(session, target_id)
    account_ids = (
        (await session.execute(select(Account.id).where(Account.target_id == target_id)))
        .scalars()
        .all()
    )
    await _ensure_no_active_checkouts(session, account_ids)
    await _shred_secrets(session, account_ids)
    await session.delete(target)
    await audit_service.record(
        session,
        actor,
        "target.delete",
        object_type="target",
        object_id=target_id,
        details={"name": target.name, "accounts_removed": len(account_ids)},
    )
    await session.commit()


# ── Accounts ──


def account_out(account: Account, active_checkouts: int = 0) -> AccountOut:
    return AccountOut(
        id=account.id,
        target=TargetBrief.model_validate(account.target),
        username=account.username,
        secret_type=account.secret_type,
        description=account.description,
        has_secret=account.secret_version > 0,
        secret_version=account.secret_version,
        secret_updated_at=account.secret_updated_at,
        requires_approval=account.requires_approval,
        exclusive_checkout=account.exclusive_checkout,
        max_checkout_minutes=account.max_checkout_minutes,
        active_checkouts=active_checkouts,
        created_at=account.created_at,
    )


async def active_checkout_counts(
    session: AsyncSession, account_ids: list[uuid.UUID]
) -> dict[uuid.UUID, int]:
    if not account_ids:
        return {}
    rows = await session.execute(
        select(Checkout.account_id, func.count())
        .where(Checkout.account_id.in_(account_ids), Checkout.status == CheckoutStatus.ACTIVE)
        .group_by(Checkout.account_id)
    )
    return dict(rows.all())


async def list_accounts(
    session: AsyncSession,
    *,
    page: int,
    page_size: int,
    target_id: uuid.UUID | None = None,
    search: str | None = None,
) -> tuple[list[AccountOut], int]:
    conditions = []
    if target_id:
        conditions.append(Account.target_id == target_id)
    if search:
        like = f"%{search.lower()}%"
        conditions.append(
            or_(
                func.lower(Account.username).like(like),
                func.lower(Target.name).like(like),
                func.lower(Target.address).like(like),
            )
        )
    base = select(Account).join(Account.target).where(*conditions)
    total = (await session.execute(select(func.count()).select_from(base.subquery()))).scalar_one()
    rows = (
        (
            await session.execute(
                base.order_by(func.lower(Target.name), func.lower(Account.username))
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        )
        .scalars()
        .all()
    )
    counts = await active_checkout_counts(session, [a.id for a in rows])
    return [account_out(a, counts.get(a.id, 0)) for a in rows], total


async def get_account(
    session: AsyncSession, account_id: uuid.UUID, *, lock: bool = False
) -> Account:
    # populate_existing: a just-created account in the identity map gets its target loaded.
    stmt = select(Account).where(Account.id == account_id).execution_options(populate_existing=True)
    if lock:
        # Lock only the account row, not the joined target.
        stmt = stmt.with_for_update(of=Account)
    account = (await session.execute(stmt)).scalar_one_or_none()
    if account is None:
        raise NotFoundError("Account not found")
    return account


async def _store_secret(session: AsyncSession, actor: Actor, account: Account, value: str) -> None:
    version = account.secret_version + 1
    await vault_service.store(
        session,
        owner_type=ACCOUNT_SECRET,
        owner_id=account.id,
        version=version,
        plaintext=value,
        created_by=actor.id,
    )
    account.secret_version = version
    account.secret_updated_at = utcnow()


async def create_account(session: AsyncSession, actor: Actor, body: AccountCreate) -> AccountOut:
    await get_target(session, body.target_id)
    account = Account(**body.model_dump(exclude={"secret"}))
    session.add(account)
    try:
        await session.flush()
    except IntegrityError as exc:
        raise ConflictError("This account already exists on the target") from exc
    if body.secret:
        await _store_secret(session, actor, account, body.secret)
    await audit_service.record(
        session,
        actor,
        "account.create",
        object_type="account",
        object_id=account.id,
        details={
            "target_id": str(body.target_id),
            "username": body.username,
            "with_secret": bool(body.secret),
        },
    )
    await session.commit()
    return account_out(await get_account(session, account.id))


async def update_account(
    session: AsyncSession, actor: Actor, account_id: uuid.UUID, body: AccountUpdate
) -> AccountOut:
    account = await get_account(session, account_id, lock=True)
    changes = body.model_dump(exclude_unset=True)
    for field, value in changes.items():
        setattr(account, field, value)
    await audit_service.record(
        session,
        actor,
        "account.update",
        object_type="account",
        object_id=account.id,
        details=changes,
    )
    await session.commit()
    counts = await active_checkout_counts(session, [account.id])
    return account_out(account, counts.get(account.id, 0))


async def set_secret(
    session: AsyncSession, actor: Actor, account_id: uuid.UUID, value: str
) -> AccountOut:
    account = await get_account(session, account_id, lock=True)
    await _store_secret(session, actor, account, value)
    await audit_service.record(
        session,
        actor,
        "secret.set",
        object_type="account",
        object_id=account.id,
        details={"version": account.secret_version},
    )
    await session.commit()
    return account_out(account)


async def delete_account(session: AsyncSession, actor: Actor, account_id: uuid.UUID) -> None:
    account = await get_account(session, account_id, lock=True)
    await _ensure_no_active_checkouts(session, [account.id])
    await _shred_secrets(session, [account.id])
    await session.delete(account)
    await audit_service.record(
        session,
        actor,
        "account.delete",
        object_type="account",
        object_id=account_id,
        details={"username": account.username, "target_id": str(account.target_id)},
    )
    await session.commit()


async def _ensure_no_active_checkouts(session: AsyncSession, account_ids: list[uuid.UUID]) -> None:
    if any((await active_checkout_counts(session, list(account_ids))).values()):
        raise ConflictError("Check in or revoke the active check-outs first")


async def _shred_secrets(session: AsyncSession, account_ids: list[uuid.UUID]) -> None:
    if account_ids:
        await session.execute(
            delete(Secret).where(
                Secret.owner_type == ACCOUNT_SECRET, Secret.owner_id.in_(account_ids)
            )
        )
