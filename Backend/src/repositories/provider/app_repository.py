"""Application identities (iam.apps) and their client secrets (iam.app_secrets)."""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import datetime
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError

from src.contracts.dto.provider.app_dto import AppDTO, AppSecretDTO, AppSecretHashDTO
from src.errors.exceptions import ConflictError
from src.models import App, AppSecret
from src.repositories.base import BaseRepository

_DUPLICATE = "An application identity with this name already exists"


def _secret_dto(row: AppSecret) -> AppSecretDTO:
    return AppSecretDTO(
        id=row.id,
        app_id=row.app_id,
        slot=row.slot,
        prefix=row.prefix,
        expires_at=row.expires_at,
        revoked_at=row.revoked_at,
        last_used_at=row.last_used_at,
        created_at=row.created_at,
    )


def _to_dto(row: App, secrets: Sequence[AppSecret] = ()) -> AppDTO:
    return AppDTO(
        id=row.id,
        name=row.name,
        description=row.description,
        client_id=row.client_id,
        enabled=row.enabled,
        ip_allowlist=tuple(row.ip_allowlist or ()),
        rate_limit_per_minute=row.rate_limit_per_minute,
        token_version=row.token_version,
        created_at=row.created_at,
        updated_at=row.updated_at,
        secrets=tuple(_secret_dto(s) for s in secrets),
    )


class AppRepository(BaseRepository):
    async def _secrets_for(self, app_ids: Sequence[uuid.UUID]) -> dict[uuid.UUID, list[AppSecret]]:
        if not app_ids:
            return {}
        rows = await self._session.scalars(
            select(AppSecret)
            .where(AppSecret.app_id.in_(list(app_ids)))
            .order_by(AppSecret.created_at.desc())
        )
        out: dict[uuid.UUID, list[AppSecret]] = {}
        for row in rows:
            out.setdefault(row.app_id, []).append(row)
        return out

    async def list(
        self, *, search: str | None, page: int, page_size: int
    ) -> tuple[list[AppDTO], int]:
        conditions = []
        if search:
            conditions.append(func.lower(App.name).like(f"%{search.lower()}%"))
        total = await self._session.scalar(select(func.count()).select_from(App).where(*conditions))
        rows = list(
            await self._session.scalars(
                select(App)
                .where(*conditions)
                .order_by(func.lower(App.name))
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        )
        secrets = await self._secrets_for([r.id for r in rows])
        return [_to_dto(r, secrets.get(r.id, ())) for r in rows], total or 0

    async def get(self, app_id: uuid.UUID, *, lock: bool = False) -> AppDTO | None:
        stmt = select(App).where(App.id == app_id)
        if lock:
            stmt = stmt.with_for_update()
        row = await self._session.scalar(stmt)
        if row is None:
            return None
        return _to_dto(row, (await self._secrets_for([row.id])).get(row.id, ()))

    async def get_by_client_id(self, client_id: str) -> AppDTO | None:
        row = await self._session.scalar(select(App).where(App.client_id == client_id))
        return _to_dto(row) if row else None

    async def names(self, app_ids: Sequence[uuid.UUID]) -> dict[uuid.UUID, str]:
        if not app_ids:
            return {}
        rows = await self._session.execute(select(App.id, App.name).where(App.id.in_(app_ids)))
        return dict(rows.all())

    async def create(self, values: dict[str, Any]) -> uuid.UUID:
        row = App(**values)
        self._session.add(row)
        try:
            await self._session.flush()
        except IntegrityError as exc:
            raise ConflictError(_DUPLICATE) from exc
        return row.id

    async def update(self, app_id: uuid.UUID, changes: dict[str, Any]) -> None:
        row = await self._session.get(App, app_id)
        for key, value in changes.items():
            setattr(row, key, value)
        try:
            await self._session.flush()
        except IntegrityError as exc:
            raise ConflictError(_DUPLICATE) from exc

    async def bump_token_version(self, app_id: uuid.UUID) -> None:
        await self._session.execute(
            update(App).where(App.id == app_id).values(token_version=App.token_version + 1)
        )

    # ── Secrets ──

    async def add_secret(self, values: dict[str, Any]) -> AppSecretDTO:
        row = AppSecret(**values)
        self._session.add(row)
        try:
            await self._session.flush()
        except IntegrityError as exc:
            raise ConflictError("This application identity already has two active secrets") from exc
        return _secret_dto(row)

    async def get_secret(self, secret_id: uuid.UUID) -> AppSecretDTO | None:
        row = await self._session.get(AppSecret, secret_id)
        return _secret_dto(row) if row else None

    async def revoke_secret(self, secret_id: uuid.UUID, when: datetime) -> None:
        await self._session.execute(
            update(AppSecret)
            .where(AppSecret.id == secret_id, AppSecret.revoked_at.is_(None))
            .values(revoked_at=when)
        )

    async def unrevoked_hashes(self, app_id: uuid.UUID) -> list[AppSecretHashDTO]:
        """Every unrevoked secret (at most two; expiry is checked by the caller)."""
        rows = await self._session.scalars(
            select(AppSecret)
            .where(AppSecret.app_id == app_id, AppSecret.revoked_at.is_(None))
            .order_by(AppSecret.slot)
        )
        return [AppSecretHashDTO(r.id, r.secret_hash, r.expires_at) for r in rows]

    async def touch_secret(self, secret_id: uuid.UUID, when: datetime) -> None:
        await self._session.execute(
            update(AppSecret).where(AppSecret.id == secret_id).values(last_used_at=when)
        )
