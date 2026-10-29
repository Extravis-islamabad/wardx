"""The startup KEK canary check (HA_DR.md §6, D10).

A node refuses to start when its KEK cannot open the install's canary: better to fail at
deploy time than to serve "secret could not be decrypted". Wrapping and unwrapping happen
in the key provider only; the canary's value is never used for anything else.
"""

from __future__ import annotations

import structlog

from src.keys.provider import KeyIntegrityError, KeyProvider, KeyProviderError
from src.repositories.keys.kek_canary_repository import KekCanaryRepository

logger = structlog.get_logger(__name__)

CANARY_AAD = b"wardx-kek-canary|v1"


class KekMismatch(RuntimeError):
    """This node's KEK cannot open the install's canary."""


class KekCanaryService:
    def __init__(self, repo: KekCanaryRepository, provider: KeyProvider) -> None:
        self._repo = repo
        self._provider = provider

    async def _prove_existing_keys(self) -> None:
        """An existing install without a canary: the KEK must open its tenant keys first,
        or a node with the wrong KEK would create the canary under that wrong KEK."""
        for wrapped, aad in await self._repo.existing_wrapped_keys():
            try:
                await self._provider.unwrap(wrapped, aad)
            except (KeyIntegrityError, KeyProviderError) as exc:
                raise KekMismatch(
                    "KEK canary check failed: no canary yet, and this node's KEK cannot open "
                    f"the install's existing tenant keys (wrapped by KEK {wrapped.key_id}). "
                    "Refusing to start."
                ) from exc

    async def check(self) -> str:
        """'created', 'ok' or 'rewrapped'; raises KekMismatch."""
        wrapped = await self._repo.get()
        if wrapped is None:
            await self._prove_existing_keys()
            _, fresh = await self._provider.generate(CANARY_AAD)
            await self._repo.insert_first(fresh)
            await self._repo.commit()
            wrapped = await self._repo.get()
            created = wrapped is not None and wrapped.blob == fresh.blob
            if created:
                logger.warning("kek_canary_created", kek_id=fresh.key_id)
                return "created"
        try:
            value = await self._provider.unwrap(wrapped, CANARY_AAD)
        except (KeyIntegrityError, KeyProviderError) as exc:
            raise KekMismatch(
                "KEK canary check failed: this node's KEK cannot open the install's canary "
                f"(wrapped by KEK {wrapped.key_id}). Refusing to start; deploy the same "
                "WARDX_VAULT_KEK (and retired KEKs) as the other nodes."
            ) from exc
        await self._repo.rollback()
        if wrapped.key_id != self._provider.active_key_id:
            # A KEK rotation: keep the canary under the active KEK while the old one is
            # still loaded as retired.
            await self._repo.rewrap(await self._provider.wrap(value, CANARY_AAD))
            await self._repo.commit()
            logger.warning("kek_canary_rewrapped", kek_id=self._provider.active_key_id)
            return "rewrapped"
        return "ok"
