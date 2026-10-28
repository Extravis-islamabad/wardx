"""Rotation jobs and their steps (access.rotation_jobs, access.rotation_job_steps).

Claiming uses ``FOR UPDATE SKIP LOCKED`` plus a per-target advisory lock, so several
scheduler processes can claim at once and at most one job runs per target.
"""

from __future__ import annotations

import uuid
import zlib
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError

from src.contracts.dto.rotation.rotation_dto import (
    CLAIMABLE_STATES,
    PENDING,
    RUNNING,
    WAITING_RELEASE,
    RotationFilterDTO,
    RotationJobDTO,
    RotationStepDTO,
)
from src.errors.exceptions import ConflictError
from src.models import Account, RotationJob, RotationJobStep, Target
from src.repositories.base import BaseRepository

_TARGET_LOCK_BASE = 0x5741_5244_0700_0000
_ACCOUNT_LOCK_BASE = 0x5741_5244_0800_0000


def _step_dto(row: RotationJobStep) -> RotationStepDTO:
    return RotationStepDTO(
        id=row.id,
        step=row.step,
        outcome=row.outcome,
        secret_version=row.secret_version,
        detail=row.detail,
        transcript=row.transcript,
        started_at=row.started_at,
        finished_at=row.finished_at,
        channel=row.channel,
    )


def _to_dto(row: RotationJob, target: Target | None, steps=()) -> RotationJobDTO:
    account = row.account
    return RotationJobDTO(
        id=row.id,
        account_id=row.account_id,
        account_username=account.username,
        target_id=account.target_id,
        target_name=target.name if target is not None else account.target.name,
        safe_id=account.safe_id,
        reason=row.reason,
        status=row.status,
        requested_by=row.requested_by,
        note=row.note,
        dry_run=row.dry_run,
        not_before=row.not_before,
        attempts=row.attempts,
        lease_until=row.lease_until,
        change_sent_at=row.change_sent_at,
        waiting_since=row.waiting_since,
        release_alerted_at=row.release_alerted_at,
        started_at=row.started_at,
        finished_at=row.finished_at,
        from_version=row.from_version,
        candidate_version=row.candidate_version,
        secret_versions_touched=list(row.secret_versions_touched or []),
        driver=row.driver,
        detail=row.detail,
        verify_result=row.verify_result,
        resolution=row.resolution,
        resolution_note=row.resolution_note,
        resolved_by=row.resolved_by,
        resolved_at=row.resolved_at,
        created_at=row.created_at,
        steps=[_step_dto(s) for s in steps],
    )


def target_lock_key(target_id: uuid.UUID) -> int:
    return _TARGET_LOCK_BASE + zlib.crc32(target_id.bytes)


def account_lock_key(account_id: uuid.UUID) -> int:
    return _ACCOUNT_LOCK_BASE + zlib.crc32(account_id.bytes)


class RotationJobRepository(BaseRepository):
    async def create(self, values: dict[str, Any]) -> uuid.UUID:
        row = RotationJob(**values)
        self._session.add(row)
        try:
            async with self._session.begin_nested():
                await self._session.flush()
        except IntegrityError as exc:
            raise ConflictError("This account already has an open rotation job") from exc
        return row.id

    async def try_account_lock(self, account_id: uuid.UUID) -> bool:
        """Take the account's rotation lock for this transaction; False if held elsewhere."""
        return bool(
            (
                await self._session.execute(
                    text("SELECT pg_try_advisory_xact_lock(:k)"),
                    {"k": account_lock_key(account_id)},
                )
            ).scalar_one()
        )

    async def account_of(self, job_id: uuid.UUID) -> uuid.UUID | None:
        return await self._session.scalar(
            select(RotationJob.account_id).where(RotationJob.id == job_id)
        )

    async def get(
        self, job_id: uuid.UUID, *, lock: bool = False, with_steps: bool = False
    ) -> RotationJobDTO | None:
        stmt = (
            select(RotationJob)
            .where(RotationJob.id == job_id)
            .execution_options(populate_existing=True)
        )
        if lock:
            stmt = stmt.with_for_update(of=RotationJob)
        row = (await self._session.execute(stmt)).unique().scalar_one_or_none()
        if row is None:
            return None
        steps = await self.steps(job_id) if with_steps else []
        return _to_dto(row, None, steps)

    async def steps(self, job_id: uuid.UUID) -> list[RotationJobStep]:
        return list(
            await self._session.scalars(
                select(RotationJobStep)
                .where(RotationJobStep.job_id == job_id)
                .order_by(RotationJobStep.id)
            )
        )

    async def open_for_account(self, account_id: uuid.UUID) -> RotationJobDTO | None:
        from src.contracts.dto.rotation.rotation_dto import OPEN_STATES

        row = (
            (
                await self._session.execute(
                    select(RotationJob).where(
                        RotationJob.account_id == account_id,
                        RotationJob.status.in_(OPEN_STATES),
                    )
                )
            )
            .unique()
            .scalar_one_or_none()
        )
        return _to_dto(row, None) if row else None

    async def list(
        self, filters: RotationFilterDTO, *, page: int, page_size: int
    ) -> tuple[list[RotationJobDTO], int]:
        conditions = []
        if filters.status:
            conditions.append(RotationJob.status == filters.status)
        if filters.reason:
            conditions.append(RotationJob.reason == filters.reason)
        if filters.account_id:
            conditions.append(RotationJob.account_id == filters.account_id)
        if filters.safe_ids is not None:
            conditions.append(Account.safe_id.in_(filters.safe_ids))
        base = select(RotationJob).join(Account, Account.id == RotationJob.account_id)
        base = base.where(*conditions)
        total = await self._session.scalar(select(func.count()).select_from(base.subquery()))
        rows = (
            (
                await self._session.execute(
                    base.order_by(RotationJob.created_at.desc())
                    .offset((page - 1) * page_size)
                    .limit(page_size)
                )
            )
            .unique()
            .scalars()
            .all()
        )
        return [_to_dto(r, None) for r in rows], total or 0

    async def update(self, job_id: uuid.UUID, changes: dict[str, Any]) -> None:
        row = await self._session.get(RotationJob, job_id)
        for key, value in changes.items():
            setattr(row, key, value)
        await self._session.flush()

    async def add_step(self, values: dict[str, Any]) -> None:
        self._session.add(RotationJobStep(**values))
        await self._session.flush()

    async def claim(
        self, worker: str, now: datetime, lease: timedelta, *, limit: int = 20
    ) -> uuid.UUID | None:
        """Claim the next due job whose target has no running job. The caller commits."""
        candidates = (
            await self._session.execute(
                select(RotationJob.id, RotationJob.target_id)
                .where(
                    RotationJob.status.in_(CLAIMABLE_STATES),
                    RotationJob.not_before <= now,
                    (RotationJob.lease_until.is_(None)) | (RotationJob.lease_until < now),
                )
                .order_by(RotationJob.not_before)
                .limit(limit)
                .with_for_update(skip_locked=True, of=RotationJob)
            )
        ).all()
        for job_id, target_id in candidates:
            if target_id is not None:
                locked = (
                    await self._session.execute(
                        text("SELECT pg_try_advisory_xact_lock(:k)"),
                        {"k": target_lock_key(target_id)},
                    )
                ).scalar_one()
                if not locked or await self._target_busy(target_id, job_id, now):
                    continue
            row = await self._session.get(RotationJob, job_id)
            row.attempts += 1
            row.claimed_by = worker
            row.lease_until = now + lease
            row.started_at = row.started_at or now
            if row.status == PENDING:
                row.status = RUNNING
            await self._session.flush()
            return job_id
        return None

    async def _target_busy(self, target_id: uuid.UUID, job_id: uuid.UUID, now: datetime) -> bool:
        return bool(
            await self._session.scalar(
                select(func.count())
                .select_from(RotationJob)
                .where(
                    RotationJob.target_id == target_id,
                    RotationJob.id != job_id,
                    RotationJob.lease_until > now,
                    RotationJob.status.in_(CLAIMABLE_STATES),
                )
            )
        )

    async def waiting(self) -> list[RotationJobDTO]:
        rows = (
            (
                await self._session.execute(
                    select(RotationJob)
                    .where(RotationJob.status == WAITING_RELEASE)
                    .with_for_update(skip_locked=True, of=RotationJob)
                )
            )
            .unique()
            .scalars()
            .all()
        )
        return [_to_dto(r, None) for r in rows]

    async def latest_change_for_account(self, account_id: uuid.UUID) -> RotationJobDTO | None:
        """The newest job that changed (or tried to change) the account's password."""
        row = (
            (
                await self._session.execute(
                    select(RotationJob)
                    .where(
                        RotationJob.account_id == account_id,
                        RotationJob.reason != "verify",
                        RotationJob.candidate_version.is_not(None),
                    )
                    .order_by(RotationJob.created_at.desc())
                    .limit(1)
                )
            )
            .unique()
            .scalar_one_or_none()
        )
        return _to_dto(row, None) if row else None
