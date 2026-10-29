"""The KEK canary row (keystore.kek_canary)."""

from __future__ import annotations

from sqlalchemy import text

from src.keys.provider import WrappedKey
from src.repositories.base import BaseRepository
from src.services.keys.tenant_key_service import key_aad


class KekCanaryRepository(BaseRepository):
    async def get(self) -> WrappedKey | None:
        row = (
            await self._session.execute(
                text("SELECT kek_id, wrap_nonce, wrapped FROM keystore.kek_canary WHERE id = 1")
            )
        ).first()
        return WrappedKey(row.kek_id, bytes(row.wrap_nonce), bytes(row.wrapped)) if row else None

    async def insert_first(self, wrapped: WrappedKey) -> None:
        """Insert unless another node created it first (theirs stands)."""
        await self._session.execute(
            text(
                "INSERT INTO keystore.kek_canary (id, kek_id, wrap_nonce, wrapped) "
                "VALUES (1, :k, :n, :w) ON CONFLICT (id) DO NOTHING"
            ),
            {"k": wrapped.key_id, "n": wrapped.nonce, "w": wrapped.blob},
        )

    async def rewrap(self, wrapped: WrappedKey) -> None:
        await self._session.execute(
            text(
                "UPDATE keystore.kek_canary SET kek_id = :k, wrap_nonce = :n, wrapped = :w, "
                "rewrapped_at = NOW() WHERE id = 1"
            ),
            {"k": wrapped.key_id, "n": wrapped.nonce, "w": wrapped.blob},
        )

    async def existing_wrapped_keys(self, limit: int = 3) -> list[tuple[WrappedKey, bytes]]:
        """A few wrapped tenant keys with their AAD: an existing install's proof that a KEK
        is the right one before a canary is first created under it."""
        rows = await self._session.execute(
            text(
                "SELECT tenant_id, purpose, version, kek_id, wrap_nonce, wrapped_key "
                "FROM keystore.tenant_keys WHERE wrapped_key IS NOT NULL "
                "ORDER BY created_at LIMIT :n"
            ),
            {"n": limit},
        )
        return [
            (
                WrappedKey(r.kek_id, bytes(r.wrap_nonce or b""), bytes(r.wrapped_key)),
                key_aad(r.tenant_id, r.purpose, r.version),
            )
            for r in rows.all()
        ]
