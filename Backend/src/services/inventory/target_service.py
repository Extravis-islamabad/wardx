"""Targets: the devices, hosts and databases privileged accounts live on."""

from __future__ import annotations

import uuid

from src.contracts.dto.inventory.target_dto import TargetDTO, TargetFilterDTO
from src.core.context import Actor
from src.core.enums import DEFAULT_PORTS, Protocol, SafePermission
from src.errors.exceptions import ForbiddenError, NotFoundError
from src.repositories.inventory.account_repository import AccountRepository
from src.repositories.inventory.target_repository import TargetRepository
from src.services.audit.audit_service import AuditService
from src.services.inventory.account_service import ACCOUNT_SECRET, ensure_no_active_checkouts
from src.services.safes.safe_access_service import SafeAccessService
from src.services.vault.vault_service import VaultService


class TargetService:
    def __init__(
        self,
        targets: TargetRepository,
        accounts: AccountRepository,
        vault: VaultService,
        audit: AuditService,
        access: SafeAccessService,
    ) -> None:
        self._targets = targets
        self._accounts = accounts
        self._vault = vault
        self._audit = audit
        self._access = access

    async def list(
        self, filters: TargetFilterDTO, *, page: int, page_size: int
    ) -> tuple[list[TargetDTO], int]:
        return await self._targets.list(filters, page=page, page_size=page_size)

    async def get(self, target_id: uuid.UUID) -> TargetDTO:
        target = await self._targets.get(target_id)
        if target is None:
            raise NotFoundError("Target not found")
        return target

    async def find_by_name(self, name: str) -> TargetDTO | None:
        """The target with this name, ignoring case (how gateway logins name targets)."""
        return await self._targets.find_by_name(name)

    async def create(self, actor: Actor, values: dict) -> TargetDTO:
        port = values.pop("port", None)
        values["port"] = port or DEFAULT_PORTS[Protocol(values["protocol"])]
        target = await self._targets.create(values)
        await self._audit.record(
            actor,
            "target.create",
            object_type="target",
            object_id=target.id,
            details={"name": target.name, "address": target.address, "platform": target.platform},
        )
        await self._targets.commit()
        return target

    async def update(self, actor: Actor, target_id: uuid.UUID, changes: dict) -> TargetDTO:
        if "protocol" in changes and "port" not in changes:
            changes["port"] = DEFAULT_PORTS[Protocol(changes["protocol"])]
        target = await self._targets.update(target_id, changes)
        if target is None:
            raise NotFoundError("Target not found")
        await self._audit.record(
            actor,
            "target.update",
            object_type="target",
            object_id=target.id,
            details={
                k: str(v) if not isinstance(v, bool | int | list) else v for k, v in changes.items()
            },
        )
        await self._targets.commit()
        return target

    async def delete(self, actor: Actor, target_id: uuid.UUID) -> None:
        target = await self.get(target_id)
        accounts = await self._accounts.list_for_target(target_id)
        # Deleting a target deletes its accounts: that needs manage_accounts on every safe
        # they sit in (a safe the actor cannot see refuses as forbidden, not as missing).
        for safe_id in {a.safe_id for a in accounts}:
            perms = await self._access.permissions(actor, safe_id)
            if SafePermission.MANAGE_ACCOUNTS not in perms:
                raise ForbiddenError(
                    "This target has accounts in safes you cannot manage; move or delete them first"
                )
        account_ids = [a.id for a in accounts]
        await ensure_no_active_checkouts(self._accounts, account_ids)
        await self._vault.shred(ACCOUNT_SECRET, account_ids)
        await self._targets.delete(target_id)
        await self._audit.record(
            actor,
            "target.delete",
            object_type="target",
            object_id=target_id,
            details={"name": target.name, "accounts_removed": len(account_ids)},
        )
        await self._targets.commit()
