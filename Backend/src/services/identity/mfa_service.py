"""TOTP enrolment, verification (web and gateway), recovery codes and resets.

Rules:
- A seed only counts once the user confirms it with a code; confirming signs
  out sessions that never proved a second factor.
- Each TOTP step works once (a conditional update, so two concurrent logins
  with the same code cannot both win); each recovery code works once.
- Failed codes count toward the same lockout as failed passwords, and the
  failure audit commits before the error is raised.
- Roles in ``mfa_required_roles`` cannot turn MFA off, and neither can a holder
  of break-glass access (it requires MFA); an administrator revokes it first.
- An administrator's MFA reset of a break-glass holder revokes the grant in the
  same transaction (audited, high alert).
"""

from __future__ import annotations

import uuid
from datetime import timedelta

from src.contracts.dto.identity.mfa_dto import MfaStatusDTO, UserMfaDTO
from src.contracts.dto.identity.user_dto import UserDTO
from src.core import totp
from src.core.config import Settings
from src.core.context import Actor
from src.core.enums import Role
from src.core.permissions import DIRECT_GRANT_ONLY
from src.errors.exceptions import (
    AccountLockedError,
    ConflictError,
    NotFoundError,
    UnauthorizedError,
)
from src.models import utcnow
from src.repositories.identity.mfa_repository import MfaRepository
from src.repositories.identity.user_repository import UserRepository
from src.services.audit.audit_service import AuditService
from src.services.identity.user_grant_service import UserGrantService
from src.services.vault.vault_service import VaultService

MFA_SECRET = "mfa_totp"


class MfaService:
    def __init__(
        self,
        mfa: MfaRepository,
        users: UserRepository,
        vault: VaultService,
        audit: AuditService,
        settings: Settings,
        grants: UserGrantService,
    ) -> None:
        self._mfa = mfa
        self._users = users
        self._vault = vault
        self._audit = audit
        self._settings = settings
        self._grants = grants

    def is_required(self, role: str) -> bool:
        return role in self._settings.mfa_required_roles

    async def is_enabled(self, user_id: uuid.UUID) -> bool:
        row = await self._mfa.get(user_id)
        return bool(row and row.enabled)

    async def status(self, user_id: uuid.UUID, role: str) -> MfaStatusDTO:
        row = await self._mfa.get(user_id)
        return MfaStatusDTO(
            enabled=bool(row and row.enabled),
            pending=bool(row and not row.enabled),
            required=self.is_required(role),
            recovery_codes_left=await self._mfa.unused_code_count(user_id),
        )

    # ── Enrolment ──

    async def start_enrolment(self, actor: Actor) -> tuple[str, str]:
        """New seed for the user's authenticator; active only after confirm_enrolment."""
        row = await self._mfa.get(actor.id, lock=True)
        if row is not None and row.enabled:
            raise ConflictError("MFA is already on; turn it off first to re-enrol")
        seed = totp.new_seed()
        version = await self._vault.next_version(MFA_SECRET, actor.id)
        await self._vault.store(
            owner_type=MFA_SECRET,
            owner_id=actor.id,
            version=version,
            plaintext=seed,
            created_by=actor.id,
        )
        if row is None:
            await self._mfa.create(
                {"user_id": actor.id, "secret_version": version, "enabled": False}
            )
        else:
            await self._mfa.update(actor.id, {"secret_version": version})
        await self._audit.record(actor, "mfa.enrol_start", object_type="user", object_id=actor.id)
        await self._mfa.commit()
        return seed, totp.provisioning_uri(seed, account=actor.username)

    async def confirm_enrolment(self, actor: Actor, code: str) -> list[str]:
        row = await self._mfa.get(actor.id, lock=True)
        if row is None or row.enabled:
            raise ConflictError("Start MFA set-up first")
        step = totp.match_step(await self._seed(row), code)
        if step is None:
            raise UnauthorizedError("That code is not valid; check the time on your phone")
        await self._mfa.update(
            actor.id, {"enabled": True, "last_used_step": step, "enrolled_at": utcnow()}
        )
        codes = await self._replace_recovery_codes(actor.id)
        user = await self._users.get(actor.id, lock=True)
        # Sessions from before MFA was on did not prove a second factor.
        await self._users.update(actor.id, {"token_version": user.token_version + 1})
        await self._audit.record(actor, "mfa.enable", object_type="user", object_id=actor.id)
        await self._mfa.commit()
        return codes

    async def regenerate_recovery_codes(self, actor: Actor, code: str) -> list[str]:
        if not await self._check_code(actor.id, code, allow_recovery=False):
            raise UnauthorizedError("That code is not valid")
        codes = await self._replace_recovery_codes(actor.id)
        await self._audit.record(
            actor, "mfa.recovery_regenerate", object_type="user", object_id=actor.id
        )
        await self._mfa.commit()
        return codes

    # ── Verification ──

    async def verify_login_code(
        self, *, user_id: uuid.UUID, code: str, source_ip: str | None, channel: str
    ) -> UserDTO:
        """Second login step, with the same lockout as passwords. Commits."""
        user = await self._users.get(user_id, lock=True)
        if user is None or not user.is_active:
            raise UnauthorizedError("Session is no longer valid")
        actor = Actor(id=user.id, username=user.username, role=Role(user.role), source_ip=source_ip)
        now = utcnow()
        if user.locked_until and user.locked_until > now:
            raise AccountLockedError(
                "Account is temporarily locked after repeated failed logins",
                {"locked_until": user.locked_until.isoformat()},
            )
        kind = await self._check_code(user.id, code)
        if kind is None:
            failed = user.failed_logins + 1
            changes: dict = {"failed_logins": failed}
            if failed >= self._settings.login_max_failures:
                changes["locked_until"] = now + timedelta(
                    minutes=self._settings.login_lockout_minutes
                )
                changes["failed_logins"] = 0
            await self._users.update(user.id, changes)
            await self._audit.record(
                actor,
                "auth.mfa",
                object_type="user",
                object_id=user.id,
                outcome="failure",
                details={"channel": channel},
            )
            await self._users.commit()
            raise UnauthorizedError("Invalid authentication code")
        user = await self._users.update(user.id, {"failed_logins": 0, "last_login_at": now})
        await self._audit.record(
            actor,
            "auth.mfa",
            object_type="user",
            object_id=user.id,
            details={"channel": channel, "method": kind},
        )
        await self._users.commit()
        return user

    # ── Turning it off ──

    async def disable_self(self, actor: Actor, code: str) -> None:
        user = await self._users.get(actor.id, lock=True)
        if self.is_required(user.role):
            raise ConflictError("Your role requires MFA; it cannot be turned off")
        if await self._grants.codenames(actor.id) & DIRECT_GRANT_ONLY:
            raise ConflictError(
                "You hold break-glass access, which requires MFA. Ask another administrator "
                "to revoke it before turning MFA off."
            )
        if not await self._check_code(actor.id, code):
            raise UnauthorizedError("That code is not valid")
        await self._remove(actor.id)
        await self._audit.record(actor, "mfa.disable", object_type="user", object_id=actor.id)
        await self._mfa.commit()

    async def admin_reset(self, actor: Actor, user_id: uuid.UUID) -> None:
        """For a user who lost their phone and recovery codes. They re-enrol at next login."""
        user = await self._users.get(user_id, lock=True)
        if user is None:
            raise NotFoundError("User not found")
        await self._remove(user_id)
        await self._users.update(user_id, {"token_version": user.token_version + 1})
        await self._audit.record(
            actor,
            "mfa.reset",
            object_type="user",
            object_id=user_id,
            details={"username": user.username},
        )
        # Break-glass requires MFA: the grant goes with it.
        await self._grants.revoke_after_mfa_reset(actor, user_id, user.username)
        await self._mfa.commit()

    # ── Internals ──

    async def _seed(self, row: UserMfaDTO) -> str:
        return await self._vault.read(
            owner_type=MFA_SECRET, owner_id=row.user_id, version=row.secret_version
        )

    async def _replace_recovery_codes(self, user_id: uuid.UUID) -> list[str]:
        codes = totp.new_recovery_codes()
        await self._mfa.replace_recovery_codes(user_id, [totp.hash_recovery(c) for c in codes])
        return codes

    async def _check_code(
        self, user_id: uuid.UUID, code: str, *, allow_recovery: bool = True
    ) -> str | None:
        """'totp' or 'recovery' when the code is good (and now spent); None otherwise."""
        row = await self._mfa.get(user_id)
        if row is None or not row.enabled:
            return None
        step = totp.match_step(await self._seed(row), code, after=row.last_used_step)
        if step is not None:
            return "totp" if await self._mfa.claim_step(user_id, step) else None
        if allow_recovery and await self._mfa.use_recovery_code(
            user_id, totp.hash_recovery(code), utcnow()
        ):
            return "recovery"
        return None

    async def _remove(self, user_id: uuid.UUID) -> None:
        await self._mfa.delete_for_user(user_id)
        await self._vault.shred(MFA_SECRET, [user_id])
