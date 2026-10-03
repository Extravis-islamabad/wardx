"""Login, token refresh, logout and password change."""

from __future__ import annotations

import uuid
from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.contracts.schemas.identity import TokenPair
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
from src.errors.exceptions import AccountLockedError, UnauthorizedError
from src.models import User, utcnow
from src.services import audit_service

_BAD_LOGIN = "Invalid username or password"


def issue_tokens(user: User, settings: Settings) -> TokenPair:
    secret = resolve_jwt_secret(settings)
    access_ttl = timedelta(minutes=settings.jwt_access_minutes)
    return TokenPair(
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
            ttl=timedelta(days=settings.jwt_refresh_days),
        ),
        expires_in=int(access_ttl.total_seconds()),
    )


async def login(
    session: AsyncSession,
    settings: Settings,
    *,
    username: str,
    password: str,
    source_ip: str | None,
) -> TokenPair:
    # The row lock makes the failure counter exact under parallel guessing.
    user = (
        await session.execute(
            select(User).where(func.lower(User.username) == username.lower()).with_for_update()
        )
    ).scalar_one_or_none()
    actor = Actor(
        id=user.id if user else None,
        username=username[:150],
        role=Role(user.role) if user else Role.USER,
        source_ip=source_ip,
    )
    now = utcnow()

    if user is None:
        await burn_password_check(password)
        await audit_service.record(
            session, actor, "auth.login", outcome="failure", details={"reason": "unknown_user"}
        )
        await session.commit()
        raise UnauthorizedError(_BAD_LOGIN)

    if user.locked_until and user.locked_until > now:
        await audit_service.record(
            session,
            actor,
            "auth.login",
            object_type="user",
            object_id=user.id,
            outcome="failure",
            details={"reason": "locked"},
        )
        await session.commit()
        raise AccountLockedError(
            "Account is temporarily locked after repeated failed logins",
            {"locked_until": user.locked_until.isoformat()},
        )

    password_ok = await verify_password(user.password_hash, password)
    if not password_ok or not user.is_active:
        reason = "inactive" if password_ok else "bad_password"
        if not password_ok:
            user.failed_logins += 1
            if user.failed_logins >= settings.login_max_failures:
                user.locked_until = now + timedelta(minutes=settings.login_lockout_minutes)
                user.failed_logins = 0
                reason = "bad_password_locked"
        await audit_service.record(
            session,
            actor,
            "auth.login",
            object_type="user",
            object_id=user.id,
            outcome="failure",
            details={"reason": reason},
        )
        await session.commit()
        raise UnauthorizedError(_BAD_LOGIN)

    user.failed_logins = 0
    user.locked_until = None
    user.last_login_at = now
    if needs_rehash(user.password_hash):
        user.password_hash = await hash_password(password)
    await audit_service.record(session, actor, "auth.login", object_type="user", object_id=user.id)
    await session.commit()
    return issue_tokens(user, settings)


async def refresh(session: AsyncSession, settings: Settings, refresh_token: str) -> TokenPair:
    claims = decode_token(
        refresh_token, secret=resolve_jwt_secret(settings), expected_type="refresh"
    )
    try:
        user = await session.get(User, uuid.UUID(claims["sub"]))
    except ValueError as exc:
        raise UnauthorizedError("Invalid token") from exc
    if user is None or not user.is_active or user.token_version != claims["tv"]:
        raise UnauthorizedError("Session is no longer valid")
    return issue_tokens(user, settings)


async def logout_everywhere(session: AsyncSession, actor: Actor) -> None:
    """Invalidate every token issued to the user so far."""
    user = await session.get(User, actor.id, with_for_update=True)
    user.token_version += 1
    await audit_service.record(
        session, actor, "auth.logout", object_type="user", object_id=actor.id
    )
    await session.commit()


async def change_password(
    session: AsyncSession, settings: Settings, actor: Actor, *, current: str, new: str
) -> TokenPair:
    user = await session.get(User, actor.id, with_for_update=True)
    if not await verify_password(user.password_hash, current):
        await audit_service.record(
            session,
            actor,
            "auth.password_change",
            object_type="user",
            object_id=user.id,
            outcome="failure",
            details={"reason": "bad_current_password"},
        )
        await session.commit()
        raise UnauthorizedError("Current password is incorrect")
    user.password_hash = await hash_password(new)
    user.token_version += 1
    await audit_service.record(
        session, actor, "auth.password_change", object_type="user", object_id=user.id
    )
    await session.commit()
    return issue_tokens(user, settings)
