"""TOTP enrolments (iam.user_mfa) and recovery codes (iam.mfa_recovery_codes)."""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import datetime
from typing import Any

from sqlalchemy import delete, func, select, update

from src.contracts.dto.identity.mfa_dto import UserMfaDTO
from src.models import MfaRecoveryCode, UserMfa
from src.repositories.base import BaseRepository


def _to_dto(row: UserMfa) -> UserMfaDTO:
    return UserMfaDTO(
        user_id=row.user_id,
        secret_version=row.secret_version,
        enabled=row.enabled,
        last_used_step=row.last_used_step,
        enrolled_at=row.enrolled_at,
    )


class MfaRepository(BaseRepository):
    async def get(self, user_id: uuid.UUID, *, lock: bool = False) -> UserMfaDTO | None:
        row = await self._session.get(UserMfa, user_id, with_for_update=lock or None)
        return _to_dto(row) if row else None

    async def create(self, values: dict[str, Any]) -> None:
        self._session.add(UserMfa(**values))
        await self._session.flush()

    async def update(self, user_id: uuid.UUID, changes: dict[str, Any]) -> None:
        row = await self._session.get(UserMfa, user_id)
        for field, value in changes.items():
            setattr(row, field, value)
        await self._session.flush()

    async def claim_step(self, user_id: uuid.UUID, step: int) -> bool:
        """Record ``step`` as used unless it (or a later one) already was.

        A conditional update: of two concurrent logins with the same code, only one wins.
        """
        claimed = await self._session.execute(
            update(UserMfa)
            .where(
                UserMfa.user_id == user_id,
                (UserMfa.last_used_step.is_(None)) | (UserMfa.last_used_step < step),
            )
            .values(last_used_step=step)
        )
        return claimed.rowcount == 1

    async def unused_code_count(self, user_id: uuid.UUID) -> int:
        return (
            await self._session.execute(
                select(func.count())
                .select_from(MfaRecoveryCode)
                .where(MfaRecoveryCode.user_id == user_id, MfaRecoveryCode.used_at.is_(None))
            )
        ).scalar_one()

    async def replace_recovery_codes(self, user_id: uuid.UUID, hashes: Sequence[str]) -> None:
        await self._session.execute(
            delete(MfaRecoveryCode).where(MfaRecoveryCode.user_id == user_id)
        )
        self._session.add_all(MfaRecoveryCode(user_id=user_id, code_hash=h) for h in hashes)
        await self._session.flush()

    async def use_recovery_code(self, user_id: uuid.UUID, code_hash: str, now: datetime) -> bool:
        """Spend an unused recovery code; False if there is none with this hash."""
        used = await self._session.execute(
            update(MfaRecoveryCode)
            .where(
                MfaRecoveryCode.user_id == user_id,
                MfaRecoveryCode.code_hash == code_hash,
                MfaRecoveryCode.used_at.is_(None),
            )
            .values(used_at=now)
            .returning(MfaRecoveryCode.id)
        )
        return used.first() is not None

    async def delete_for_user(self, user_id: uuid.UUID) -> None:
        """Remove the user's enrolment and recovery codes."""
        await self._session.execute(
            delete(MfaRecoveryCode).where(MfaRecoveryCode.user_id == user_id)
        )
        await self._session.execute(delete(UserMfa).where(UserMfa.user_id == user_id))
