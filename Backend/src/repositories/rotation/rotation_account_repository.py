"""The account, target and safe side of rotation: state, policy, holders, due work."""

from __future__ import annotations

import uuid
from dataclasses import replace
from datetime import datetime
from typing import Any

from sqlalchemy import and_, func, or_, select

from src.contracts.dto.rotation.rotation_dto import (
    CONFIRMED_UNTRUSTWORTHY,
    HIGH_RISK_EMPTY_PASSWORD,
    OPEN_STATES,
    OUT_OF_SYNC,
    VERIFY_UNTRUSTWORTHY,
    RotationAccountDTO,
    RotationTargetDTO,
    SafeRotationPolicyDTO,
)
from src.core.enums import CheckoutStatus, Protocol
from src.models import Account, Checkout, GatewaySession, RotationJob, Safe, Target
from src.repositories.base import BaseRepository
from src.repositories.identity.user_names import display_names

SAFE_POLICY_FIELDS = (
    "rotate_after_use",
    "rotation_interval_days",
    "verify_interval_hours",
    "auto_reconcile",
    "maintenance_window",
    "max_release_wait_minutes",
)


def account_dto(row: Account) -> RotationAccountDTO:
    return RotationAccountDTO(
        id=row.id,
        username=row.username,
        secret_type=row.secret_type,
        safe_id=row.safe_id,
        secret_version=row.secret_version,
        password_length=row.password_length,
        rotation_interval_days=row.rotation_interval_days,
        rotate_after_use=row.rotate_after_use,
        reconcile_account_id=row.reconcile_account_id,
        sync_status=row.sync_status,
        rotation_status=row.rotation_status,
        last_rotated_at=row.last_rotated_at,
        last_verified_at=row.last_verified_at,
        last_verify_method=row.last_verify_method,
        last_rotation_status=row.last_rotation_status,
        unreachable_count=row.unreachable_count,
        risk_flags=list(row.risk_flags or []),
        created_at=row.created_at,
        risk_accepted_by=row.risk_accepted_by,
        risk_accepted_at=row.risk_accepted_at,
        risk_accepted_reason=row.risk_accepted_reason,
    )


def target_dto(row: Target) -> RotationTargetDTO:
    return RotationTargetDTO(
        id=row.id,
        name=row.name,
        address=row.address,
        port=row.port,
        platform=row.platform,
        protocol=row.protocol,
        is_active=row.is_active,
        rotation_allowed=row.rotation_allowed,
        policy_overrides=dict(row.policy_overrides or {}),
        ssh_host_key=row.ssh_host_key,
    )


def policy_dto(row: Safe) -> SafeRotationPolicyDTO:
    return SafeRotationPolicyDTO(safe_id=row.id, **{f: getattr(row, f) for f in SAFE_POLICY_FIELDS})


def _rotatable():
    """Accounts the scheduler may touch: both switches' target half, active, not Telnet."""
    return and_(
        Target.rotation_allowed,
        Target.is_active,
        Target.protocol != Protocol.TELNET,
        Account.secret_version > 0,
        Account.secret_type == "password",
        Account.sync_status != VERIFY_UNTRUSTWORTHY,
        ~select(RotationJob.id)
        .where(RotationJob.account_id == Account.id, RotationJob.status.in_(OPEN_STATES))
        .exists(),
    )


class RotationAccountRepository(BaseRepository):
    async def get(self, account_id: uuid.UUID, *, lock: bool = False) -> RotationAccountDTO | None:
        stmt = (
            select(Account)
            .where(Account.id == account_id)
            .execution_options(populate_existing=True)
        )
        if lock:
            stmt = stmt.with_for_update(of=Account)
        row = (await self._session.execute(stmt)).unique().scalar_one_or_none()
        return account_dto(row) if row else None

    async def target_of(self, account_id: uuid.UUID) -> RotationTargetDTO | None:
        row = await self._session.scalar(
            select(Target)
            .join(Account, Account.target_id == Target.id)
            .where(Account.id == account_id)
            .execution_options(populate_existing=True)
        )
        return target_dto(row) if row else None

    async def target_id_of(self, account_id: uuid.UUID) -> uuid.UUID | None:
        return await self._session.scalar(select(Account.target_id).where(Account.id == account_id))

    async def safe_policy(self, safe_id: uuid.UUID) -> SafeRotationPolicyDTO | None:
        row = await self._session.get(Safe, safe_id, populate_existing=True)
        return policy_dto(row) if row else None

    async def save_safe_policy(self, safe_id: uuid.UUID, values: dict[str, Any]) -> None:
        row = await self._session.get(Safe, safe_id)
        for key in SAFE_POLICY_FIELDS:
            setattr(row, key, values[key])
        await self._session.flush()

    async def update(self, account_id: uuid.UUID, changes: dict[str, Any]) -> None:
        row = await self._session.get(Account, account_id)
        for key, value in changes.items():
            setattr(row, key, value)
        await self._session.flush()

    async def holders(self, account_id: uuid.UUID) -> dict[str, int]:
        """Who holds the account: active check-outs (normal, emergency) and live sessions."""
        row = (
            await self._session.execute(
                select(
                    select(func.count())
                    .select_from(Checkout)
                    .where(
                        Checkout.account_id == account_id,
                        Checkout.status == CheckoutStatus.ACTIVE,
                        ~Checkout.emergency,
                    )
                    .scalar_subquery(),
                    select(func.count())
                    .select_from(Checkout)
                    .where(
                        Checkout.account_id == account_id,
                        Checkout.status == CheckoutStatus.ACTIVE,
                        Checkout.emergency,
                    )
                    .scalar_subquery(),
                    select(func.count())
                    .select_from(GatewaySession)
                    .where(
                        GatewaySession.account_id == account_id,
                        GatewaySession.status == "active",
                    )
                    .scalar_subquery(),
                )
            )
        ).one()
        return {"checkouts": row[0], "emergency": row[1], "sessions": row[2]}

    async def accounts_with_safe(self, account_ids: list[uuid.UUID]) -> list[RotationAccountDTO]:
        if not account_ids:
            return []
        rows = await self._session.scalars(select(Account).where(Account.id.in_(account_ids)))
        return [account_dto(r) for r in rows.unique()]

    async def due_for_rotation(self, now: datetime, limit: int) -> list[RotationAccountDTO]:
        """Accounts whose effective interval (the shorter of safe and account) has passed."""
        interval = func.least(Account.rotation_interval_days, Safe.rotation_interval_days)
        since = func.coalesce(
            Account.last_rotated_at, Account.secret_updated_at, Account.created_at
        )
        rows = await self._session.scalars(
            select(Account)
            .join(Target, Target.id == Account.target_id)
            .join(Safe, Safe.id == Account.safe_id)
            .where(
                _rotatable(),
                Safe.is_active,
                interval.is_not(None),
                since + func.make_interval(0, 0, 0, interval) <= now,
            )
            .limit(limit)
        )
        return [account_dto(r) for r in rows.unique()]

    async def due_for_verify(self, now: datetime, limit: int) -> list[RotationAccountDTO]:
        last = func.coalesce(Account.last_verify_attempt_at, Account.last_verified_at)
        never = last.is_(None)
        overdue = last + func.make_interval(0, 0, 0, 0, Safe.verify_interval_hours) <= now
        rows = await self._session.scalars(
            select(Account)
            .join(Target, Target.id == Account.target_id)
            .join(Safe, Safe.id == Account.safe_id)
            .where(_rotatable(), Safe.is_active, or_(never, overdue))
            .order_by(last.asc().nulls_first())
            .limit(limit)
        )
        return [account_dto(r) for r in rows.unique()]

    async def unscanned(self, limit: int) -> list[RotationAccountDTO]:
        """Password accounts whose current secret the empty-password scan has not seen."""
        rows = await self._session.scalars(
            select(Account)
            .where(
                Account.secret_type == "password",
                Account.secret_version > 0,
                Account.risk_checked_version != Account.secret_version,
            )
            .limit(limit)
        )
        return [account_dto(r) for r in rows.unique()]

    async def attention_accounts(
        self, safe_ids: frozenset[uuid.UUID] | None
    ) -> tuple[list[RotationAccountDTO], ...]:
        """(out of sync, verify untrustworthy, confirmed untrustworthy, empty password)."""
        scope = [] if safe_ids is None else [Account.safe_id.in_(safe_ids)]

        async def _where(*cond) -> list[RotationAccountDTO]:
            rows = await self._session.scalars(select(Account).where(*cond, *scope).limit(100))
            return [account_dto(r) for r in rows.unique()]

        confirmed = await _where(Account.sync_status == CONFIRMED_UNTRUSTWORTHY)
        names = await display_names(self._session, (str(a.risk_accepted_by) for a in confirmed))
        confirmed = [
            replace(a, risk_accepted_by_name=names.get(str(a.risk_accepted_by))) for a in confirmed
        ]
        return (
            await _where(Account.sync_status == OUT_OF_SYNC),
            await _where(Account.sync_status == VERIFY_UNTRUSTWORTHY),
            confirmed,
            await _where(Account.risk_flags.any(HIGH_RISK_EMPTY_PASSWORD)),
        )
