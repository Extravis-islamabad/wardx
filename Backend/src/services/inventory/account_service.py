"""Privileged accounts, including storing their secrets in the vault."""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from src.contracts.dto.inventory.account_dto import AccountDTO, AccountFilterDTO
from src.core.context import Actor
from src.errors.exceptions import ConflictError, NotFoundError
from src.models import utcnow
from src.repositories.inventory.account_repository import AccountRepository
from src.repositories.inventory.target_repository import TargetRepository
from src.services.audit.audit_service import AuditService
from src.services.vault.vault_service import VaultService

# vault.secrets owner_type for account credentials.
ACCOUNT_SECRET = "account"


async def ensure_no_active_checkouts(
    accounts: AccountRepository, account_ids: Sequence[uuid.UUID]
) -> None:
    if any((await accounts.active_checkout_counts(account_ids)).values()):
        raise ConflictError("Check in or revoke the active check-outs first")


class AccountService:
    def __init__(
        self,
        accounts: AccountRepository,
        targets: TargetRepository,
        vault: VaultService,
        audit: AuditService,
    ) -> None:
        self._accounts = accounts
        self._targets = targets
        self._vault = vault
        self._audit = audit

    async def list(
        self, filters: AccountFilterDTO, *, page: int, page_size: int
    ) -> tuple[list[AccountDTO], int]:
        return await self._accounts.list(filters, page=page, page_size=page_size)

    async def get(self, account_id: uuid.UUID, *, lock: bool = False) -> AccountDTO:
        account = await self._accounts.get(account_id, lock=lock)
        if account is None:
            raise NotFoundError("Account not found")
        return account

    async def list_for_target(self, target_id: uuid.UUID) -> list[AccountDTO]:
        return await self._accounts.list_for_target(target_id)

    async def create(self, actor: Actor, values: dict, secret: str | None) -> AccountDTO:
        if await self._targets.get(values["target_id"]) is None:
            raise NotFoundError("Target not found")
        account_id = await self._accounts.create(values)
        if secret:
            await self._store_secret(actor, await self.get(account_id, lock=True), secret)
        await self._audit.record(
            actor,
            "account.create",
            object_type="account",
            object_id=account_id,
            details={
                "target_id": str(values["target_id"]),
                "username": values["username"],
                "with_secret": bool(secret),
            },
        )
        await self._accounts.commit()
        return await self.get(account_id)

    async def update(self, actor: Actor, account_id: uuid.UUID, changes: dict) -> AccountDTO:
        await self.get(account_id, lock=True)
        await self._accounts.update(account_id, changes)
        await self._audit.record(
            actor,
            "account.update",
            object_type="account",
            object_id=account_id,
            details=changes,
        )
        await self._accounts.commit()
        return await self.get(account_id)

    async def set_secret(self, actor: Actor, account_id: uuid.UUID, value: str) -> AccountDTO:
        account = await self.get(account_id, lock=True)
        version = await self._store_secret(actor, account, value)
        await self._audit.record(
            actor,
            "secret.set",
            object_type="account",
            object_id=account_id,
            details={"version": version},
        )
        await self._accounts.commit()
        return await self.get(account_id)

    async def delete(self, actor: Actor, account_id: uuid.UUID) -> None:
        account = await self.get(account_id, lock=True)
        await ensure_no_active_checkouts(self._accounts, [account_id])
        await self._vault.shred(ACCOUNT_SECRET, [account_id])
        await self._accounts.delete(account_id)
        await self._audit.record(
            actor,
            "account.delete",
            object_type="account",
            object_id=account_id,
            details={"username": account.username, "target_id": str(account.target_id)},
        )
        await self._accounts.commit()

    async def _store_secret(self, actor: Actor, account: AccountDTO, value: str) -> int:
        """Store the next secret version. The caller holds the account row lock."""
        version = account.secret_version + 1
        await self._vault.store(
            owner_type=ACCOUNT_SECRET,
            owner_id=account.id,
            version=version,
            plaintext=value,
            created_by=actor.id,
        )
        await self._accounts.update(
            account.id, {"secret_version": version, "secret_updated_at": utcnow()}
        )
        return version
