"""What an application identity may fetch: accounts in active safes where the app is a
member holding ``fetch``, on active targets (docs/phase1/CREDENTIAL_PROVIDER.md §3, §4)."""

from __future__ import annotations

import uuid
from collections.abc import Iterable

from sqlalchemy import and_, exists, func, select

from src.contracts.dto.provider.credential_dto import FetchCandidateDTO, FetchQueryDTO
from src.core.enums import PrincipalType, SafePermission
from src.models import Account, RotationJob, Safe, SafeMember, Target
from src.repositories.base import BaseRepository

_NEEDS_ATTENTION = "needs_attention"


def _candidates(app_id: uuid.UUID):
    membership = and_(
        SafeMember.safe_id == Account.safe_id,
        SafeMember.principal_type == PrincipalType.APP,
        SafeMember.principal_key == str(app_id),
        SafeMember.permissions.any(SafePermission.FETCH.value),
    )
    return (
        select(Account, Target, Safe)
        .join(Target, Target.id == Account.target_id)
        .join(Safe, Safe.id == Account.safe_id)
        .where(exists().where(membership), Safe.is_active, Target.is_active)
    )


def _to_dto(account: Account, target: Target, safe: Safe) -> FetchCandidateDTO:
    return FetchCandidateDTO(
        account_id=account.id,
        username=account.username,
        secret_type=account.secret_type,
        secret_version=account.secret_version,
        risk_flags=tuple(account.risk_flags or ()),
        sync_status=account.sync_status,
        rotation_status=account.rotation_status,
        target_id=target.id,
        target_name=target.name,
        target_address=target.address,
        target_external_ref=target.external_ref,
        safe_id=safe.id,
        approval_required=safe.approval_required,
        allow_app_fetch=safe.allow_app_fetch,
        app_cache_seconds=safe.app_cache_seconds,
    )


class CredentialRepository(BaseRepository):
    async def find(
        self, app_id: uuid.UUID, query: FetchQueryDTO, secret_types: Iterable[str]
    ) -> list[FetchCandidateDTO]:
        stmt = _candidates(app_id).where(Account.secret_type.in_(list(secret_types)))
        if query.external_ref:
            stmt = stmt.where(Target.external_ref == query.external_ref)
        elif query.address:
            stmt = stmt.where(func.lower(Target.address) == query.address.lower())
        else:
            stmt = stmt.where(func.lower(Target.name) == (query.name or "").lower())
        if query.username is not None:
            stmt = stmt.where(Account.username == query.username)
        # At most a few rows matter: two or more is already ambiguous.
        rows = await self._session.execute(stmt.order_by(Account.id).limit(10))
        return [_to_dto(*row) for row in rows.all()]

    async def by_account(
        self, app_id: uuid.UUID, account_id: uuid.UUID
    ) -> FetchCandidateDTO | None:
        row = (
            await self._session.execute(_candidates(app_id).where(Account.id == account_id))
        ).one_or_none()
        return _to_dto(*row) if row else None

    async def rotation_needs_attention(self, account_id: uuid.UUID) -> bool:
        return bool(
            await self._session.scalar(
                select(
                    exists().where(
                        RotationJob.account_id == account_id,
                        RotationJob.status == _NEEDS_ATTENTION,
                    )
                )
            )
        )
