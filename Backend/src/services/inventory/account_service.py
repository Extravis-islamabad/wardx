"""Privileged accounts, including storing their secrets in the vault.

Safe rules (docs/phase1/SAFES_AND_APPROVALS.md):
- Listing and reading show only accounts in safes where the caller holds
  ``list``; any other account reads as 404.
- Creating, editing, setting a secret and deleting need ``manage_accounts`` on
  the account's safe, and on the destination safe too when an edit moves it.
- New accounts without a safe go into the Default safe (still needing
  ``manage_accounts`` there).
- A password account never stores an empty (or blank) password: WardX refuses it.
  Existing empty ones are flagged high_risk_empty_password by the scheduler's scan.
- A reconcile account (rotation) is another password account on the same target that
  is not itself reconciled through this one.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import replace

from src.contracts.dto.inventory.account_dto import AccountDTO, AccountFilterDTO
from src.core.context import Actor
from src.core.enums import DEFAULT_SAFE_ID, SafePermission
from src.errors.exceptions import AppError, ConflictError, NotFoundError
from src.models import utcnow
from src.repositories.inventory.account_repository import AccountRepository
from src.repositories.inventory.target_repository import TargetRepository
from src.services.audit.audit_service import AuditService
from src.services.safes.safe_access_service import SafeAccessService
from src.services.vault.vault_service import VaultService

# vault.secrets owner_type for account credentials.
ACCOUNT_SECRET = "account"
HIGH_RISK_EMPTY_PASSWORD = "high_risk_empty_password"


class EmptySecretRefused(AppError):
    status_code = 422
    code = "empty_secret"


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
        access: SafeAccessService,
    ) -> None:
        self._accounts = accounts
        self._targets = targets
        self._vault = vault
        self._audit = audit
        self._access = access

    async def list(
        self, actor: Actor, filters: AccountFilterDTO, *, page: int, page_size: int
    ) -> tuple[list[AccountDTO], int]:
        visible = await self._access.listable_safe_ids(actor)
        filters = replace(filters, safe_ids=visible)
        return await self._accounts.list(filters, page=page, page_size=page_size)

    async def list_any_safe(
        self,
        actor: Actor,
        filters: AccountFilterDTO,
        *,
        page: int,
        page_size: int,
        reason: str | None = None,
    ) -> tuple[list[AccountDTO], int]:
        """Every account, whatever its safe: only for break-glass holders (the router gates).
        Every call is audited (who, when, the filters and an optional reason); no alert."""
        rows, total = await self._accounts.list(
            replace(filters, safe_ids=None), page=page, page_size=page_size
        )
        await self._audit.record(
            actor,
            "account.emergency_list",
            object_type="account",
            details={
                "search": filters.search,
                "target_id": str(filters.target_id) if filters.target_id else None,
                "page": page,
                "page_size": page_size,
                "reason": reason,
                "results": total,
            },
        )
        await self._accounts.commit()
        return rows, total

    async def listable_safe_ids(self, actor: Actor) -> frozenset[uuid.UUID]:
        return await self._access.listable_safe_ids(actor)

    async def safe_ids_for(self, account_ids: list[uuid.UUID]) -> dict[uuid.UUID, uuid.UUID]:
        return await self._accounts.safe_ids_for(account_ids)

    async def get_visible(self, actor: Actor, account_id: uuid.UUID) -> AccountDTO:
        """The account, if the actor may list its safe; otherwise 404."""
        account = await self.get(account_id)
        await self._access.require(actor, account.safe_id)
        return account

    async def authorise(
        self, actor: Actor, account: AccountDTO, *any_of: SafePermission
    ) -> frozenset[str]:
        """The actor's permissions on the account's safe: 404 unlisted, 403 lacking any_of."""
        return await self._access.require(actor, account.safe_id, *any_of)

    async def _manageable(
        self, actor: Actor, account_id: uuid.UUID, *, lock: bool = True
    ) -> AccountDTO:
        account = await self.get(account_id, lock=lock)
        await self.authorise(actor, account, SafePermission.MANAGE_ACCOUNTS)
        return account

    async def get(self, account_id: uuid.UUID, *, lock: bool = False) -> AccountDTO:
        account = await self._accounts.get(account_id, lock=lock)
        if account is None:
            raise NotFoundError("Account not found")
        return account

    async def list_for_target(self, target_id: uuid.UUID) -> list[AccountDTO]:
        return await self._accounts.list_for_target(target_id)

    async def create(self, actor: Actor, values: dict, secret: str | None) -> AccountDTO:
        values = {**values, "safe_id": values.get("safe_id") or DEFAULT_SAFE_ID}
        await self._access.require(
            actor, values["safe_id"], SafePermission.MANAGE_ACCOUNTS, what="Safe"
        )
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
            safe_id=values["safe_id"],
            details={
                "target_id": str(values["target_id"]),
                "safe_id": str(values["safe_id"]),
                "username": values["username"],
                "with_secret": bool(secret),
            },
        )
        await self._accounts.commit()
        return await self.get(account_id)

    async def update(self, actor: Actor, account_id: uuid.UUID, changes: dict) -> AccountDTO:
        account = await self._manageable(actor, account_id)
        if changes.get("safe_id") is None:
            changes.pop("safe_id", None)
        elif changes["safe_id"] != account.safe_id:
            # Moving: the destination safe must be manageable too.
            await self._access.require(
                actor, changes["safe_id"], SafePermission.MANAGE_ACCOUNTS, what="Safe"
            )
        else:
            changes.pop("safe_id")
        if changes.get("reconcile_account_id") is not None:
            await self._check_reconcile(account, changes["reconcile_account_id"])
        await self._accounts.update(account_id, changes)
        details = {k: str(v) if isinstance(v, uuid.UUID) else v for k, v in changes.items()}
        if "safe_id" in changes:
            details["from_safe_id"] = str(account.safe_id)
        await self._audit.record(
            actor,
            "account.update",
            object_type="account",
            object_id=account_id,
            # A move is recorded in the safe the account left (details name the target).
            safe_id=account.safe_id,
            details=details,
        )
        await self._accounts.commit()
        return await self.get(account_id)

    async def set_secret(self, actor: Actor, account_id: uuid.UUID, value: str) -> AccountDTO:
        account = await self._manageable(actor, account_id)
        version = await self._store_secret(actor, account, value)
        await self._audit.record(
            actor,
            "secret.set",
            object_type="account",
            object_id=account_id,
            safe_id=account.safe_id,
            details={"version": version},
        )
        await self._accounts.commit()
        return await self.get(account_id)

    async def delete(self, actor: Actor, account_id: uuid.UUID) -> None:
        account = await self._manageable(actor, account_id)
        await ensure_no_active_checkouts(self._accounts, [account_id])
        await self._vault.shred(ACCOUNT_SECRET, [account_id])
        await self._accounts.delete(account_id)
        await self._audit.record(
            actor,
            "account.delete",
            object_type="account",
            object_id=account_id,
            safe_id=account.safe_id,
            details={
                "username": account.username,
                "target_id": str(account.target_id),
                "safe_id": str(account.safe_id),
            },
        )
        await self._accounts.commit()

    async def _check_reconcile(self, account: AccountDTO, reconcile_id: uuid.UUID) -> None:
        if reconcile_id == account.id:
            raise ConflictError("An account cannot be its own reconcile account")
        other = await self._accounts.get(reconcile_id)
        if other is None or other.target_id != account.target_id:
            raise ConflictError("The reconcile account must be an account on the same target")
        if other.reconcile_account_id == account.id:
            raise ConflictError("Those two accounts would reconcile each other")
        if other.secret_type != "password":
            raise ConflictError("The reconcile account must be a password account")

    async def _store_secret(self, actor: Actor, account: AccountDTO, value: str) -> int:
        """Store the next secret version. The caller holds the account row lock."""
        if account.secret_type == "password" and not value.strip():
            raise EmptySecretRefused("A password account cannot store an empty password")
        # Rotation keeps abandoned candidates as versions too: never reuse a number.
        version = await self._vault.next_version(ACCOUNT_SECRET, account.id)
        await self._vault.store(
            owner_type=ACCOUNT_SECRET,
            owner_id=account.id,
            version=version,
            plaintext=value,
            created_by=actor.id,
        )
        await self._accounts.update(
            account.id,
            {
                "secret_version": version,
                "secret_updated_at": utcnow(),
                "risk_flags": [f for f in account.risk_flags if f != HIGH_RISK_EMPTY_PASSWORD],
                "risk_checked_version": version,
                # A secret set by hand is unknown to the device until a verify; an
                # untrustworthy verify still needs its review (confirm or reconcile).
                "sync_status": account.sync_status
                if account.sync_status == "verify_untrustworthy"
                else "unknown",
            },
        )
        return version
