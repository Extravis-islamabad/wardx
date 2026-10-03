"""Reading gateway sessions, kill requests, command rules and host-key pins."""

from __future__ import annotations

import uuid
from pathlib import Path

from anyio import to_thread
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.contracts.schemas.sessions import (
    CommandRuleCreate,
    CommandRuleUpdate,
    CommandTestResult,
    SessionOut,
)
from src.core.context import Actor
from src.core.enums import Role
from src.errors.exceptions import ConflictError, ForbiddenError, NotFoundError
from src.gateway.policy import CommandPolicy
from src.gateway.recorder import file_sha256
from src.models import Account, CommandRule, GatewaySession, SessionCommand, Target, utcnow
from src.services import audit_service

_SEE_ALL = (Role.ADMIN, Role.AUDITOR)

# ── Sessions ──


def session_out(row: GatewaySession) -> SessionOut:
    return SessionOut(
        id=row.id,
        user_id=row.user_id,
        username=row.user.username,
        account_id=row.account_id,
        account_username=row.account_username,
        target_id=row.target_id,
        target_name=row.target_name,
        target_address=row.target_address,
        protocol=row.protocol,
        mode=row.mode,
        exec_command=row.exec_command,
        client_ip=row.client_ip,
        gateway_node=row.gateway_node,
        status=row.status,
        started_at=row.started_at,
        ended_at=row.ended_at,
        close_reason=row.close_reason,
        terminate_requested_at=row.terminate_requested_at,
        has_recording=row.recording_path is not None,
        recording_sha256=row.recording_sha256,
        recording_bytes=row.recording_bytes,
        bytes_from_target=row.bytes_from_target,
        commands_count=row.commands_count,
        blocked_count=row.blocked_count,
    )


async def list_sessions(
    session: AsyncSession,
    actor: Actor,
    *,
    page: int,
    page_size: int,
    status: str | None = None,
    mine: bool = False,
    search: str | None = None,
) -> tuple[list[SessionOut], int]:
    conditions = []
    if mine or not actor.has_role(*_SEE_ALL):
        conditions.append(GatewaySession.user_id == actor.id)
    if status:
        conditions.append(GatewaySession.status == status)
    if search:
        like = f"%{search.lower()}%"
        conditions.append(
            or_(
                func.lower(GatewaySession.target_name).like(like),
                func.lower(GatewaySession.account_username).like(like),
                func.lower(GatewaySession.target_address).like(like),
            )
        )
    total = (
        await session.execute(select(func.count()).select_from(GatewaySession).where(*conditions))
    ).scalar_one()
    rows = (
        (
            await session.execute(
                select(GatewaySession)
                .where(*conditions)
                .order_by(GatewaySession.started_at.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        )
        .unique()
        .scalars()
        .all()
    )
    return [session_out(r) for r in rows], total


async def get_session_row(
    session: AsyncSession, actor: Actor, session_id: uuid.UUID
) -> GatewaySession:
    row = (
        (await session.execute(select(GatewaySession).where(GatewaySession.id == session_id)))
        .unique()
        .scalar_one_or_none()
    )
    if row is None:
        raise NotFoundError("Session not found")
    if row.user_id != actor.id and not actor.has_role(*_SEE_ALL):
        raise ForbiddenError("Not your session")
    return row


async def list_commands(
    session: AsyncSession, actor: Actor, session_id: uuid.UUID
) -> list[SessionCommand]:
    await get_session_row(session, actor, session_id)
    return list(
        (
            await session.execute(
                select(SessionCommand)
                .where(SessionCommand.session_id == session_id)
                .order_by(SessionCommand.id)
            )
        ).scalars()
    )


async def recording(
    session: AsyncSession, actor: Actor, session_id: uuid.UUID, recording_root: Path
) -> tuple[Path, bool]:
    """The recording file and whether it still matches the hash taken when it closed."""
    row = await get_session_row(session, actor, session_id)
    if row.recording_path is None:
        raise NotFoundError("This session has no recording")

    def _locate() -> Path | None:
        # Only serve files inside the recording directory.
        path = Path(row.recording_path).resolve()
        ok = path.is_relative_to(recording_root.resolve()) and path.is_file()
        return path if ok else None

    path = await to_thread.run_sync(_locate)
    if path is None:
        raise NotFoundError("Recording file is missing")
    verified = False
    if row.recording_sha256:
        verified = await to_thread.run_sync(file_sha256, path) == row.recording_sha256
    await audit_service.record(
        session,
        actor,
        "session.recording_view",
        object_type="session",
        object_id=row.id,
        details={"verified": verified},
    )
    await session.commit()
    return path, verified


async def request_terminate(
    session: AsyncSession, actor: Actor, session_id: uuid.UUID
) -> SessionOut:
    row = (
        (
            await session.execute(
                select(GatewaySession)
                .where(GatewaySession.id == session_id)
                .with_for_update(of=GatewaySession)
            )
        )
        .unique()
        .scalar_one_or_none()
    )
    if row is None:
        raise NotFoundError("Session not found")
    if row.status != "active":
        raise ConflictError(f"Session is already {row.status}")
    if row.terminate_requested_at is None:
        row.terminate_requested_at = utcnow()
        row.terminate_requested_by = actor.id
        await audit_service.record(
            session,
            actor,
            "session.terminate",
            object_type="session",
            object_id=row.id,
            details={"user_id": str(row.user_id), "target": row.target_name},
        )
    await session.commit()
    return session_out(row)


# ── Command rules ──


async def list_rules(session: AsyncSession) -> list[CommandRule]:
    return list(
        (await session.execute(select(CommandRule).order_by(CommandRule.created_at))).scalars()
    )


async def create_rule(session: AsyncSession, actor: Actor, body: CommandRuleCreate) -> CommandRule:
    if body.account_id and await session.get(Account, body.account_id) is None:
        raise NotFoundError("Account not found")
    if body.target_id and await session.get(Target, body.target_id) is None:
        raise NotFoundError("Target not found")
    rule = CommandRule(**body.model_dump(), created_by=actor.id)
    session.add(rule)
    await session.flush()
    await audit_service.record(
        session,
        actor,
        "command_rule.create",
        object_type="command_rule",
        object_id=rule.id,
        details={k: str(v) for k, v in body.model_dump().items() if v is not None},
    )
    await session.commit()
    return rule


async def update_rule(
    session: AsyncSession, actor: Actor, rule_id: uuid.UUID, body: CommandRuleUpdate
) -> CommandRule:
    rule = await session.get(CommandRule, rule_id, with_for_update=True)
    if rule is None:
        raise NotFoundError("Rule not found")
    changes = body.model_dump(exclude_unset=True)
    for field, value in changes.items():
        setattr(rule, field, value)
    await audit_service.record(
        session,
        actor,
        "command_rule.update",
        object_type="command_rule",
        object_id=rule.id,
        details=changes,
    )
    await session.commit()
    return rule


async def delete_rule(session: AsyncSession, actor: Actor, rule_id: uuid.UUID) -> None:
    rule = await session.get(CommandRule, rule_id)
    if rule is None:
        raise NotFoundError("Rule not found")
    await session.delete(rule)
    await audit_service.record(
        session,
        actor,
        "command_rule.delete",
        object_type="command_rule",
        object_id=rule_id,
        details={"pattern": rule.pattern},
    )
    await session.commit()


async def test_command(
    session: AsyncSession, command: str, account_id: uuid.UUID | None
) -> CommandTestResult:
    """Which rule, if any, would block ``command`` (on ``account_id``, or anywhere)."""
    conditions = [CommandRule.is_active]
    if account_id is not None:
        account = await session.get(Account, account_id)
        if account is None:
            raise NotFoundError("Account not found")
        conditions += [
            or_(CommandRule.account_id.is_(None), CommandRule.account_id == account.id),
            or_(CommandRule.target_id.is_(None), CommandRule.target_id == account.target_id),
            or_(CommandRule.platform.is_(None), CommandRule.platform == account.target.platform),
        ]
    rows = (
        await session.execute(
            select(CommandRule.id, CommandRule.pattern, CommandRule.description).where(*conditions)
        )
    ).all()
    rule = CommandPolicy.build(rows).check(command)
    return CommandTestResult(
        blocked=rule is not None,
        rule_id=rule.id if rule else None,
        description=rule.description if rule else None,
    )


# ── Host keys ──


async def reset_host_key(session: AsyncSession, actor: Actor, target_id: uuid.UUID) -> Target:
    target = await session.get(Target, target_id, with_for_update=True)
    if target is None:
        raise NotFoundError("Target not found")
    previous = target.ssh_host_key_fingerprint
    target.ssh_host_key = None
    target.ssh_host_key_fingerprint = None
    target.ssh_host_key_learned_at = None
    await audit_service.record(
        session,
        actor,
        "target.host_key_reset",
        object_type="target",
        object_id=target.id,
        details={"previous_fingerprint": previous},
    )
    await session.commit()
    return target
