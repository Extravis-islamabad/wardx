"""Break-glass: reveal any account's secret, whatever its safe, with a reason.

Rules:
- Needs ``access.emergency`` (a direct grant; no role holds it). At the moment of
  use the holder must still be a local, active, MFA-enrolled user, so break-glass
  never depends on the directory.
- Rotation never blocks it: it reveals the account's current version, with a notice
  when a rotation needs attention or the last verify was untrustworthy.
- A reason of at least 20 characters. The reveal records an emergency check-out
  (exclusivity does not block it: that is the point of break-glass), is audited as
  ``secret.emergency_reveal`` and raises a high-severity alert, all in one
  transaction. A refused attempt is audited as a failure.
"""

from __future__ import annotations

import uuid
from datetime import timedelta

from src.contracts.dto.access.checkout_dto import RevealedSecretDTO
from src.core.context import Actor
from src.core.enums import CheckoutStatus
from src.core.permissions import ACCESS_EMERGENCY
from src.errors.exceptions import ConflictError, ForbiddenError
from src.models import utcnow
from src.repositories.access.checkout_repository import CheckoutRepository
from src.repositories.identity.mfa_repository import MfaRepository
from src.repositories.identity.user_repository import UserRepository
from src.services.audit.audit_service import AuditService
from src.services.inventory.account_service import ACCOUNT_SECRET, AccountService
from src.services.rotation.rotation_guard import RotationGuard
from src.services.security.alert_service import AlertService
from src.services.vault.vault_service import VaultService

MIN_REASON = 20
EMERGENCY_MINUTES = 60


class EmergencyAccessService:
    def __init__(
        self,
        accounts: AccountService,
        checkouts: CheckoutRepository,
        users: UserRepository,
        mfa: MfaRepository,
        vault: VaultService,
        alerts: AlertService,
        audit: AuditService,
        rotation: RotationGuard,
    ) -> None:
        self._rotation = rotation
        self._accounts = accounts
        self._checkouts = checkouts
        self._users = users
        self._mfa = mfa
        self._vault = vault
        self._alerts = alerts
        self._audit = audit

    async def _refuse(self, actor: Actor, account_id: uuid.UUID, reason: str, exc: Exception):
        await self._audit.record(
            actor,
            "secret.emergency_reveal",
            object_type="account",
            object_id=account_id,
            outcome="failure",
            details={"reason": reason},
        )
        await self._checkouts.commit()
        raise exc

    async def reveal(self, actor: Actor, account_id: uuid.UUID, reason: str) -> RevealedSecretDTO:
        reason = reason.strip()
        if not actor.can(ACCESS_EMERGENCY):
            raise ForbiddenError("Break-glass access is not granted to you")
        user = await self._users.get(actor.id)
        mfa = await self._mfa.get(actor.id)
        if user is None or user.auth_source != "local" or not user.is_active:
            await self._refuse(
                actor,
                account_id,
                "holder_not_local",
                ForbiddenError("Break-glass needs an active local WardX account"),
            )
        if not (mfa and mfa.enabled):
            await self._refuse(
                actor,
                account_id,
                "holder_without_mfa",
                ForbiddenError("Break-glass needs MFA on your account"),
            )
        if len(reason) < MIN_REASON:
            raise ConflictError(f"Give a reason of at least {MIN_REASON} characters")

        account = await self._accounts.get(account_id, lock=True)
        if account.secret_version == 0:
            raise ConflictError("No secret is stored for this account yet")
        holders = await self._checkouts.active_for_account(account.id)
        if any(h.user_id == actor.id for h in holders):
            raise ConflictError("You already hold this account checked out; check it in first")
        now = utcnow()
        minutes = min(EMERGENCY_MINUTES, account.max_checkout_minutes)
        checkout_id = await self._checkouts.create(
            {
                "account_id": account.id,
                "user_id": actor.id,
                "reason": reason,
                "secret_version": account.secret_version,
                "checked_out_at": now,
                "expires_at": now + timedelta(minutes=minutes),
                "status": CheckoutStatus.ACTIVE,
                "emergency": True,
            }
        )
        # Always the current version (accounts.secret_version), whatever a rotation is
        # doing: an unpromoted candidate is never revealed (ROTATION.md §14).
        value = await self._vault.read(
            owner_type=ACCOUNT_SECRET, owner_id=account.id, version=account.secret_version
        )
        notice = await self._rotation.break_glass_notice(account.id)
        details = {
            "account_id": str(account.id),
            "safe_id": str(account.safe_id),
            "target": account.target.name,
            "username": account.username,
            "version": account.secret_version,
            "reason": reason,
        }
        await self._audit.record(
            actor,
            "secret.emergency_reveal",
            object_type="checkout",
            object_id=checkout_id,
            safe_id=account.safe_id,
            details=details,
        )
        await self._alerts.raise_alert(
            actor,
            kind="break_glass.used",
            message=(
                f"{actor.username} used break-glass on {account.username}@"
                f"{account.target.name} (safe {account.safe.name})"
            ),
            object_type="account",
            object_id=account.id,
            details={**details, "checkout_id": str(checkout_id)},
        )
        await self._checkouts.commit()
        return RevealedSecretDTO(
            checkout_id=checkout_id,
            username=account.username,
            secret_type=account.secret_type,
            value=value,
            expires_at=now + timedelta(minutes=minutes),
            notice=notice,
        )
