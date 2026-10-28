"""Command rules (access.command_rules) the gateway enforces."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import or_, select

from src.contracts.dto.sessions.command_rule_dto import CommandRuleDTO, RuleScopeDTO
from src.models import CommandRule
from src.repositories.base import BaseRepository


def _to_dto(row: CommandRule) -> CommandRuleDTO:
    return CommandRuleDTO(
        id=row.id,
        pattern=row.pattern,
        description=row.description,
        account_id=row.account_id,
        target_id=row.target_id,
        platform=row.platform,
        is_active=row.is_active,
        created_at=row.created_at,
    )


class CommandRuleRepository(BaseRepository):
    async def list(self) -> list[CommandRuleDTO]:
        rows = await self._session.scalars(select(CommandRule).order_by(CommandRule.created_at))
        return [_to_dto(r) for r in rows]

    async def get(self, rule_id: uuid.UUID, *, lock: bool = False) -> CommandRuleDTO | None:
        row = await self._session.get(CommandRule, rule_id, with_for_update=lock or None)
        return _to_dto(row) if row else None

    async def create(self, values: dict[str, Any]) -> CommandRuleDTO:
        row = CommandRule(**values)
        self._session.add(row)
        await self._session.flush()
        return _to_dto(row)

    async def update(self, rule_id: uuid.UUID, changes: dict[str, Any]) -> CommandRuleDTO:
        row = await self._session.get(CommandRule, rule_id)
        for field, value in changes.items():
            setattr(row, field, value)
        await self._session.flush()
        return _to_dto(row)

    async def delete(self, rule_id: uuid.UUID) -> None:
        row = await self._session.get(CommandRule, rule_id)
        if row is not None:
            await self._session.delete(row)
            await self._session.flush()

    async def active_rules(
        self, scope: RuleScopeDTO | None
    ) -> list[tuple[uuid.UUID, str, str | None]]:
        """(id, pattern, description) of active rules that apply in ``scope``; every
        active rule when ``scope`` is None."""
        conditions = [CommandRule.is_active]
        if scope is not None:
            conditions += [
                or_(CommandRule.account_id.is_(None), CommandRule.account_id == scope.account_id),
                or_(CommandRule.target_id.is_(None), CommandRule.target_id == scope.target_id),
                or_(CommandRule.platform.is_(None), CommandRule.platform == scope.platform),
            ]
        rows = await self._session.execute(
            select(CommandRule.id, CommandRule.pattern, CommandRule.description).where(*conditions)
        )
        return [(rid, pattern, description) for rid, pattern, description in rows.all()]
