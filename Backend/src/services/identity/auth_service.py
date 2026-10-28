"""Login (password, then MFA when on), token refresh, logout and password change.

Rules:
- Directory users (and unknown names, when a directory is on) are checked
  against LDAP; local accounts never are, so a directory cannot take one over.
- Repeated failures lock the account for a while; every failure is audited and
  the audit commits before the error is raised.
- Tokens carry the user's token_version; bumping it signs the user out
  everywhere (logout, password change, role change, MFA turned on).
"""

from __future__ import annotations

import uuid
from datetime import timedelta

from src.contracts.dto.identity.token_dto import LoginResultDTO, TokenPairDTO
from src.contracts.dto.identity.user_dto import UserDTO
from src.core.config import Settings, resolve_jwt_secret
from src.core.context import Actor
from src.core.enums import Role
from src.core.security import (
    burn_password_check,
    create_token,
    decode_token,
    hash_password,
    needs_rehash,
    verify_password,
)
from src.directory.ldap_client import DirectoryAuthFailed, normalise_dn
from src.errors.exceptions import (
    AccountLockedError,
    ConflictError,
    DirectoryUnavailable,
    UnauthorizedError,
)
from src.models import utcnow
from src.repositories.identity.group_cache_repository import GroupCacheRepository
from src.repositories.identity.user_repository import UserRepository
from src.services.audit.audit_service import AuditService
from src.services.directory.directory_service import DirectoryService
from src.services.identity.mfa_service import MfaService

_BAD_LOGIN = "Invalid username or password"


class AuthService:
    def __init__(
        self,
        users: UserRepository,
        mfa: MfaService,
        directory: DirectoryService,
        audit: AuditService,
        settings: Settings,
        group_cache: GroupCacheRepository,
    ) -> None:
        self._users = users
        self._mfa = mfa
        self._directory = directory
        self._audit = audit
        self._settings = settings
        self._group_cache = group_cache

    def issue_tokens(self, user: UserDTO) -> TokenPairDTO:
        secret = resolve_jwt_secret(self._settings)
        access_ttl = timedelta(minutes=self._settings.jwt_access_minutes)
        return TokenPairDTO(
            access_token=create_token(
                secret=secret,
                user_id=user.id,
                token_version=user.token_version,
                token_type="access",
                ttl=access_ttl,
            ),
            refresh_token=create_token(
                secret=secret,
                user_id=user.id,
                token_version=user.token_version,
                token_type="refresh",
                ttl=timedelta(days=self._settings.jwt_refresh_days),
            ),
            expires_in=int(access_ttl.total_seconds()),
        )

    async def tokens_for(self, user_id: uuid.UUID) -> TokenPairDTO:
        """Fresh tokens for a signed-in user (after their token_version changed)."""
        user = await self._users.get(user_id)
        if user is None:
            raise UnauthorizedError("Session is no longer valid")
        return self.issue_tokens(user)

    async def authenticate(
        self, *, username: str, password: str, source_ip: str | None, channel: str = "web"
    ) -> UserDTO:
        """Check a password with lockout and auditing; commits, returns the user or raises."""
        # The row lock makes the failure counter exact under parallel guessing.
        user = await self._users.find_by_username(username, lock=True)
        actor = Actor(
            id=user.id if user else None,
            username=username[:150],
            role=Role(user.role) if user else Role.USER,
            source_ip=source_ip,
        )
        now = utcnow()

        async def _fail(reason: str) -> None:
            await self._audit.record(
                actor,
                "auth.login",
                object_type="user" if user else None,
                object_id=user.id if user else None,
                outcome="failure",
                details={"reason": reason, "channel": channel},
            )
            await self._users.commit()

        # Directory users (and unknown names, when a directory is on) go to LDAP;
        # local accounts never do, so a directory cannot take one over.
        use_directory = (user is None or user.auth_source == "ldap") and (
            await self._directory.is_enabled()
        )

        if user is None and not use_directory:
            await burn_password_check(password)
            await _fail("unknown_user")
            raise UnauthorizedError(_BAD_LOGIN)

        if user is not None and user.locked_until and user.locked_until > now:
            await _fail("locked")
            raise AccountLockedError(
                "Account is temporarily locked after repeated failed logins",
                {"locked_until": user.locked_until.isoformat()},
            )

        reason = "bad_password"
        if use_directory:
            try:
                found = await self._directory.authenticate(username, password)
            except DirectoryAuthFailed as exc:
                password_ok, reason = False, f"directory: {exc}"
            except DirectoryUnavailable:
                await _fail("directory_unavailable")
                raise
            else:
                if user is None:
                    # The directory's canonical name may differ from what was typed.
                    user = await self._users.find_by_username(found.username, lock=True)
                    if user is not None and user.auth_source != "ldap":
                        await _fail("directory_name_taken_by_local_user")
                        raise UnauthorizedError(_BAD_LOGIN)
                user = await self._directory.upsert_user(user, found)
                # Safe memberships by directory group read this cache.
                await self._group_cache.store(user.id, (normalise_dn(g) for g in found.groups), now)
                actor = Actor(
                    id=user.id, username=user.username, role=Role(user.role), source_ip=source_ip
                )
                password_ok = True
        elif user.auth_source == "ldap":
            # Directory switched off: directory users cannot sign in with anything.
            await burn_password_check(password)
            password_ok, reason = False, "directory_disabled"
        else:
            password_ok = await verify_password(user.password_hash, password)

        if not password_ok or user is None or not user.is_active:
            if password_ok and user is not None:
                reason = "inactive"
            elif user is not None:
                failed = user.failed_logins + 1
                changes: dict = {"failed_logins": failed}
                if failed >= self._settings.login_max_failures:
                    changes["locked_until"] = now + timedelta(
                        minutes=self._settings.login_lockout_minutes
                    )
                    changes["failed_logins"] = 0
                    reason += " (locked)"
                await self._users.update(user.id, changes)
            await _fail(reason)
            raise UnauthorizedError(_BAD_LOGIN)

        success: dict = {"failed_logins": 0, "locked_until": None, "last_login_at": now}
        if user.auth_source == "local" and needs_rehash(user.password_hash):
            success["password_hash"] = await hash_password(password)
        user = await self._users.update(user.id, success)
        await self._audit.record(
            actor,
            "auth.login",
            object_type="user",
            object_id=user.id,
            details={"channel": channel, "source": user.auth_source},
        )
        await self._users.commit()
        return user

    async def login(self, *, username: str, password: str, source_ip: str | None) -> LoginResultDTO:
        user = await self.authenticate(username=username, password=password, source_ip=source_ip)
        if await self._mfa.is_enabled(user.id):
            token = create_token(
                secret=resolve_jwt_secret(self._settings),
                user_id=user.id,
                token_version=user.token_version,
                token_type="mfa",
                ttl=timedelta(minutes=self._settings.mfa_token_minutes),
            )
            return LoginResultDTO(mfa_required=True, mfa_token=token)
        return LoginResultDTO(
            tokens=self.issue_tokens(user),
            mfa_enrollment_required=self._mfa.is_required(user.role),
        )

    async def complete_mfa(
        self, *, mfa_token: str, code: str, source_ip: str | None
    ) -> LoginResultDTO:
        claims = decode_token(
            mfa_token, secret=resolve_jwt_secret(self._settings), expected_type="mfa"
        )
        try:
            user_id = uuid.UUID(claims["sub"])
        except ValueError as exc:
            raise UnauthorizedError("Invalid token") from exc
        current = await self._users.get(user_id)
        if current is None or current.token_version != claims["tv"]:
            raise UnauthorizedError("Sign in again")
        user = await self._mfa.verify_login_code(
            user_id=user_id, code=code, source_ip=source_ip, channel="web"
        )
        return LoginResultDTO(tokens=self.issue_tokens(user))

    async def refresh(self, refresh_token: str) -> TokenPairDTO:
        claims = decode_token(
            refresh_token, secret=resolve_jwt_secret(self._settings), expected_type="refresh"
        )
        try:
            user = await self._users.get(uuid.UUID(claims["sub"]))
        except ValueError as exc:
            raise UnauthorizedError("Invalid token") from exc
        if user is None or not user.is_active or user.token_version != claims["tv"]:
            raise UnauthorizedError("Session is no longer valid")
        return self.issue_tokens(user)

    async def current_user(self, access_token: str) -> UserDTO:
        """The active user an access token belongs to, or UnauthorizedError."""
        claims = decode_token(
            access_token, secret=resolve_jwt_secret(self._settings), expected_type="access"
        )
        try:
            user_id = uuid.UUID(claims["sub"])
        except ValueError as exc:
            raise UnauthorizedError("Invalid token") from exc
        user = await self._users.get(user_id)
        if user is None or not user.is_active or user.token_version != claims["tv"]:
            raise UnauthorizedError("Session is no longer valid")
        return user

    async def logout_everywhere(self, actor: Actor) -> None:
        """Invalidate every token issued to the user so far."""
        user = await self._users.get(actor.id, lock=True)
        await self._users.update(actor.id, {"token_version": user.token_version + 1})
        await self._audit.record(actor, "auth.logout", object_type="user", object_id=actor.id)
        await self._users.commit()

    async def change_password(self, actor: Actor, *, current: str, new: str) -> TokenPairDTO:
        user = await self._users.get(actor.id, lock=True)
        if user.auth_source != "local":
            raise ConflictError("Your password is managed by the company directory")
        if not await verify_password(user.password_hash, current):
            await self._audit.record(
                actor,
                "auth.password_change",
                object_type="user",
                object_id=user.id,
                outcome="failure",
                details={"reason": "bad_current_password"},
            )
            await self._users.commit()
            raise UnauthorizedError("Current password is incorrect")
        user = await self._users.update(
            user.id,
            {"password_hash": await hash_password(new), "token_version": user.token_version + 1},
        )
        await self._audit.record(
            actor, "auth.password_change", object_type="user", object_id=user.id
        )
        await self._users.commit()
        return self.issue_tokens(user)
