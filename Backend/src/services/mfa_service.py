"""TOTP enrolment, verification (web and gateway), recovery codes and resets."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.core import totp
from src.core.config import Settings
from src.core.context import Actor
from src.core.enums import Role
from src.errors.exceptions import (
    AccountLockedError,
    ConflictError,
    NotFoundError,
    UnauthorizedError,
)
from src.models import MfaRecoveryCode, Secret, User, UserMfa, utcnow
from src.services import audit_service, vault_service

MFA_SECRET = "mfa_totp"


@dataclass(frozen=True)
class MfaStatus:
    enabled: bool
    pending: bool
    required: bool
    recovery_codes_left: int


async def get_mfa(session: AsyncSession, user_id: uuid.UUID) -> UserMfa | None:
    return await session.get(UserMfa, user_id)


async def is_enabled(session: AsyncSession, user_id: uuid.UUID) -> bool:
    row = await get_mfa(session, user_id)
    return bool(row and row.enabled)


def is_required(settings: Settings, role: str) -> bool:
    return role in settings.mfa_required_roles


async def status(session: AsyncSession, settings: Settings, user: User) -> MfaStatus:
    row = await get_mfa(session, user.id)
    left = (
        await session.execute(
            select(func.count())
            .select_from(MfaRecoveryCode)
            .where(MfaRecoveryCode.user_id == user.id, MfaRecoveryCode.used_at.is_(None))
        )
    ).scalar_one()
    return MfaStatus(
        enabled=bool(row and row.enabled),
        pending=bool(row and not row.enabled),
        required=is_required(settings, user.role),
        recovery_codes_left=left,
    )


async def _next_secret_version(session: AsyncSession, user_id: uuid.UUID) -> int:
    current = (
        await session.execute(
            select(func.max(Secret.version)).where(
                Secret.owner_type == MFA_SECRET, Secret.owner_id == user_id
            )
        )
    ).scalar_one()
    return (current or 0) + 1


async def _seed(session: AsyncSession, row: UserMfa) -> str:
    return await vault_service.read(
        session, owner_type=MFA_SECRET, owner_id=row.user_id, version=row.secret_version
    )


# ── Enrolment ──


async def start_enrolment(session: AsyncSession, actor: Actor) -> tuple[str, str]:
    """New seed for the user's authenticator; active only after confirm_enrolment."""
    row = await session.get(UserMfa, actor.id, with_for_update=True)
    if row is not None and row.enabled:
        raise ConflictError("MFA is already on; turn it off first to re-enrol")
    seed = totp.new_seed()
    version = await _next_secret_version(session, actor.id)
    await vault_service.store(
        session,
        owner_type=MFA_SECRET,
        owner_id=actor.id,
        version=version,
        plaintext=seed,
        created_by=actor.id,
    )
    if row is None:
        session.add(UserMfa(user_id=actor.id, secret_version=version, enabled=False))
    else:
        row.secret_version = version
    await audit_service.record(
        session, actor, "mfa.enrol_start", object_type="user", object_id=actor.id
    )
    await session.commit()
    return seed, totp.provisioning_uri(seed, account=actor.username)


async def confirm_enrolment(session: AsyncSession, actor: Actor, code: str) -> list[str]:
    row = await session.get(UserMfa, actor.id, with_for_update=True)
    if row is None or row.enabled:
        raise ConflictError("Start MFA set-up first")
    step = totp.match_step(await _seed(session, row), code)
    if step is None:
        raise UnauthorizedError("That code is not valid; check the time on your phone")
    row.enabled = True
    row.last_used_step = step
    row.enrolled_at = utcnow()
    codes = await _replace_recovery_codes(session, actor.id)
    user = await session.get(User, actor.id, with_for_update=True)
    # Sessions from before MFA was on did not prove a second factor.
    user.token_version += 1
    await audit_service.record(session, actor, "mfa.enable", object_type="user", object_id=actor.id)
    await session.commit()
    return codes


async def _replace_recovery_codes(session: AsyncSession, user_id: uuid.UUID) -> list[str]:
    await session.execute(delete(MfaRecoveryCode).where(MfaRecoveryCode.user_id == user_id))
    codes = totp.new_recovery_codes()
    session.add_all(
        MfaRecoveryCode(user_id=user_id, code_hash=totp.hash_recovery(c)) for c in codes
    )
    await session.flush()
    return codes


async def regenerate_recovery_codes(session: AsyncSession, actor: Actor, code: str) -> list[str]:
    if not await _check_code(session, actor.id, code, allow_recovery=False):
        raise UnauthorizedError("That code is not valid")
    codes = await _replace_recovery_codes(session, actor.id)
    await audit_service.record(
        session, actor, "mfa.recovery_regenerate", object_type="user", object_id=actor.id
    )
    await session.commit()
    return codes


# ── Verification ──


async def _check_code(
    session: AsyncSession, user_id: uuid.UUID, code: str, *, allow_recovery: bool = True
) -> str | None:
    """'totp' or 'recovery' when the code is good (and now spent); None otherwise."""
    row = await get_mfa(session, user_id)
    if row is None or not row.enabled:
        return None
    step = totp.match_step(await _seed(session, row), code, after=row.last_used_step)
    if step is not None:
        # Conditional update: two concurrent logins with the same code, only one wins.
        claimed = await session.execute(
            update(UserMfa)
            .where(
                UserMfa.user_id == user_id,
                (UserMfa.last_used_step.is_(None)) | (UserMfa.last_used_step < step),
            )
            .values(last_used_step=step)
        )
        return "totp" if claimed.rowcount == 1 else None
    if allow_recovery:
        used = await session.execute(
            update(MfaRecoveryCode)
            .where(
                MfaRecoveryCode.user_id == user_id,
                MfaRecoveryCode.code_hash == totp.hash_recovery(code),
                MfaRecoveryCode.used_at.is_(None),
            )
            .values(used_at=utcnow())
            .returning(MfaRecoveryCode.id)
        )
        if used.first() is not None:
            return "recovery"
    return None


async def verify_login_code(
    session: AsyncSession,
    settings: Settings,
    *,
    user_id: uuid.UUID,
    code: str,
    source_ip: str | None,
    channel: str,
) -> User:
    """Second login step, with the same lockout as passwords. Commits."""
    user = await session.get(User, user_id, with_for_update=True)
    if user is None or not user.is_active:
        raise UnauthorizedError("Session is no longer valid")
    actor = Actor(id=user.id, username=user.username, role=Role(user.role), source_ip=source_ip)
    now = utcnow()
    if user.locked_until and user.locked_until > now:
        raise AccountLockedError(
            "Account is temporarily locked after repeated failed logins",
            {"locked_until": user.locked_until.isoformat()},
        )
    kind = await _check_code(session, user.id, code)
    if kind is None:
        user.failed_logins += 1
        if user.failed_logins >= settings.login_max_failures:
            user.locked_until = now + timedelta(minutes=settings.login_lockout_minutes)
            user.failed_logins = 0
        await audit_service.record(
            session,
            actor,
            "auth.mfa",
            object_type="user",
            object_id=user.id,
            outcome="failure",
            details={"channel": channel},
        )
        await session.commit()
        raise UnauthorizedError("Invalid authentication code")
    user.failed_logins = 0
    user.last_login_at = now
    await audit_service.record(
        session,
        actor,
        "auth.mfa",
        object_type="user",
        object_id=user.id,
        details={"channel": channel, "method": kind},
    )
    await session.commit()
    return user


# ── Turning it off ──


async def _remove(session: AsyncSession, user_id: uuid.UUID) -> None:
    await session.execute(delete(MfaRecoveryCode).where(MfaRecoveryCode.user_id == user_id))
    await session.execute(delete(UserMfa).where(UserMfa.user_id == user_id))
    await session.execute(
        delete(Secret).where(Secret.owner_type == MFA_SECRET, Secret.owner_id == user_id)
    )


async def disable_self(session: AsyncSession, settings: Settings, actor: Actor, code: str) -> None:
    user = await session.get(User, actor.id, with_for_update=True)
    if is_required(settings, user.role):
        raise ConflictError("Your role requires MFA; it cannot be turned off")
    if not await _check_code(session, actor.id, code):
        raise UnauthorizedError("That code is not valid")
    await _remove(session, actor.id)
    await audit_service.record(
        session, actor, "mfa.disable", object_type="user", object_id=actor.id
    )
    await session.commit()


async def admin_reset(session: AsyncSession, actor: Actor, user_id: uuid.UUID) -> None:
    """For a user who lost their phone and recovery codes. They re-enrol at next login."""
    user = await session.get(User, user_id, with_for_update=True)
    if user is None:
        raise NotFoundError("User not found")
    await _remove(session, user_id)
    user.token_version += 1
    await audit_service.record(
        session,
        actor,
        "mfa.reset",
        object_type="user",
        object_id=user_id,
        details={"username": user.username},
    )
    await session.commit()
