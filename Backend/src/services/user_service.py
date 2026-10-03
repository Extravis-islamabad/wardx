"""User administration and first-admin bootstrap."""

from __future__ import annotations

import os
import secrets
import uuid

import structlog
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.contracts.schemas.identity import UserCreate, UserUpdate
from src.core.config import DEV_STATE_DIR, Settings
from src.core.context import SYSTEM_ACTOR, Actor
from src.core.enums import Role
from src.core.security import hash_password
from src.errors.exceptions import ConflictError, NotFoundError
from src.models import User
from src.services import audit_service

logger = structlog.get_logger(__name__)


async def list_users(
    session: AsyncSession, *, page: int, page_size: int, search: str | None = None
) -> tuple[list[User], int]:
    conditions = []
    if search:
        like = f"%{search.lower()}%"
        conditions.append(
            func.lower(User.username).like(like)
            | func.lower(func.coalesce(User.full_name, "")).like(like)
        )
    total = (
        await session.execute(select(func.count()).select_from(User).where(*conditions))
    ).scalar_one()
    rows = (
        (
            await session.execute(
                select(User)
                .where(*conditions)
                .order_by(func.lower(User.username))
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        )
        .scalars()
        .all()
    )
    return list(rows), total


async def get_user(session: AsyncSession, user_id: uuid.UUID, *, lock: bool = False) -> User:
    user = await session.get(User, user_id, with_for_update=lock)
    if user is None:
        raise NotFoundError("User not found")
    return user


async def create_user(session: AsyncSession, actor: Actor, body: UserCreate) -> User:
    user = User(
        username=body.username,
        email=body.email,
        full_name=body.full_name,
        role=body.role.value,
        password_hash=await hash_password(body.password),
    )
    session.add(user)
    try:
        await session.flush()
    except IntegrityError as exc:
        raise ConflictError("Username already exists") from exc
    await audit_service.record(
        session,
        actor,
        "user.create",
        object_type="user",
        object_id=user.id,
        details={"username": user.username, "role": user.role},
    )
    await session.commit()
    return user


async def _active_admins(session: AsyncSession) -> int:
    return (
        await session.execute(
            select(func.count()).select_from(User).where(User.role == Role.ADMIN, User.is_active)
        )
    ).scalar_one()


async def update_user(
    session: AsyncSession, actor: Actor, user_id: uuid.UUID, body: UserUpdate
) -> User:
    user = await get_user(session, user_id, lock=True)
    changes = body.model_dump(exclude_unset=True)
    demoting = user.role == Role.ADMIN and (
        changes.get("role", Role.ADMIN) != Role.ADMIN or changes.get("is_active") is False
    )
    if demoting and user.is_active and await _active_admins(session) <= 1:
        raise ConflictError("Cannot remove the last active administrator")
    if user.id == actor.id and changes.get("is_active") is False:
        raise ConflictError("You cannot deactivate your own account")

    for field, value in changes.items():
        setattr(user, field, value.value if isinstance(value, Role) else value)
    if "is_active" in changes:
        user.disabled_reason = None if user.is_active else "admin"
    if "role" in changes or changes.get("is_active") is False:
        # Role or access changed: make existing tokens re-authenticate.
        user.token_version += 1
    await audit_service.record(
        session,
        actor,
        "user.update",
        object_type="user",
        object_id=user.id,
        details={k: (v.value if isinstance(v, Role) else v) for k, v in changes.items()},
    )
    await session.commit()
    return user


async def reset_password(
    session: AsyncSession, actor: Actor, user_id: uuid.UUID, new_password: str
) -> None:
    user = await get_user(session, user_id, lock=True)
    if user.auth_source != "local":
        raise ConflictError("This user signs in through the directory; reset it there")
    user.password_hash = await hash_password(new_password)
    user.token_version += 1
    user.failed_logins = 0
    user.locked_until = None
    await audit_service.record(
        session, actor, "user.password_reset", object_type="user", object_id=user.id
    )
    await session.commit()


async def bootstrap_admin(session: AsyncSession, settings: Settings) -> None:
    """Create the first administrator when the user table is empty."""
    if (await session.execute(select(func.count()).select_from(User))).scalar_one() > 0:
        return
    password = settings.bootstrap_admin_password
    if not password:
        if settings.is_production:
            logger.warning(
                "bootstrap_admin_skipped", reason="WARDX_BOOTSTRAP_ADMIN_PASSWORD not set"
            )
            return
        # Development: generate one and leave it in a 0600 file, never in the log.
        password = secrets.token_urlsafe(18)
        DEV_STATE_DIR.mkdir(mode=0o700, exist_ok=True)
        path = DEV_STATE_DIR / "initial-admin-password"
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as fh:
            fh.write(password + "\n")
        logger.info("bootstrap_admin_password_written", path=str(path))
    user = User(
        username=settings.bootstrap_admin_username,
        role=Role.ADMIN.value,
        full_name="Administrator",
        password_hash=await hash_password(password),
    )
    session.add(user)
    await session.flush()
    await audit_service.record(
        session,
        SYSTEM_ACTOR,
        "user.bootstrap_admin",
        object_type="user",
        object_id=user.id,
        details={"username": user.username},
    )
    await session.commit()
    logger.info("bootstrap_admin_created", username=user.username)
