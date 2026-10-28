"""Command rules the gateway enforces, and testing a command against them.

A rule is scoped to one account, one target, one platform or nothing (global);
the request schema enforces the single scope and a valid pattern.
"""

from __future__ import annotations

import uuid

from src.contracts.dto.sessions.command_rule_dto import (
    CommandRuleDTO,
    CommandTestResultDTO,
    RuleScopeDTO,
)
from src.core.context import Actor
from src.errors.exceptions import NotFoundError
from src.gateway.policy import CommandPolicy
from src.repositories.inventory.account_repository import AccountRepository
from src.repositories.inventory.target_repository import TargetRepository
from src.repositories.sessions.command_rule_repository import CommandRuleRepository
from src.services.audit.audit_service import AuditService


class CommandRuleService:
    def __init__(
        self,
        rules: CommandRuleRepository,
        accounts: AccountRepository,
        targets: TargetRepository,
        audit: AuditService,
    ) -> None:
        self._rules = rules
        self._accounts = accounts
        self._targets = targets
        self._audit = audit

    async def list(self) -> list[CommandRuleDTO]:
        return await self._rules.list()

    async def create(self, actor: Actor, values: dict) -> CommandRuleDTO:
        if values.get("account_id") and await self._accounts.get(values["account_id"]) is None:
            raise NotFoundError("Account not found")
        if values.get("target_id") and await self._targets.get(values["target_id"]) is None:
            raise NotFoundError("Target not found")
        rule = await self._rules.create({**values, "created_by": actor.id})
        await self._audit.record(
            actor,
            "command_rule.create",
            object_type="command_rule",
            object_id=rule.id,
            details={k: str(v) for k, v in values.items() if v is not None},
        )
        await self._rules.commit()
        return rule

    async def update(self, actor: Actor, rule_id: uuid.UUID, changes: dict) -> CommandRuleDTO:
        if await self._rules.get(rule_id, lock=True) is None:
            raise NotFoundError("Rule not found")
        rule = await self._rules.update(rule_id, changes)
        await self._audit.record(
            actor,
            "command_rule.update",
            object_type="command_rule",
            object_id=rule.id,
            details=changes,
        )
        await self._rules.commit()
        return rule

    async def delete(self, actor: Actor, rule_id: uuid.UUID) -> None:
        rule = await self._rules.get(rule_id)
        if rule is None:
            raise NotFoundError("Rule not found")
        await self._rules.delete(rule_id)
        await self._audit.record(
            actor,
            "command_rule.delete",
            object_type="command_rule",
            object_id=rule_id,
            details={"pattern": rule.pattern},
        )
        await self._rules.commit()

    async def policy_for(self, scope: RuleScopeDTO | None) -> CommandPolicy:
        """The policy for commands run in ``scope`` (every active rule when None)."""
        return CommandPolicy.build(await self._rules.active_rules(scope))

    async def test_command(
        self, command: str, account_id: uuid.UUID | None
    ) -> CommandTestResultDTO:
        """Which rule, if any, would block ``command`` (on ``account_id``, or anywhere)."""
        scope = None
        if account_id is not None:
            account = await self._accounts.get(account_id)
            if account is None:
                raise NotFoundError("Account not found")
            scope = RuleScopeDTO(
                account_id=account.id,
                target_id=account.target_id,
                platform=account.target.platform,
            )
        rule = (await self.policy_for(scope)).check(command)
        return CommandTestResultDTO(
            blocked=rule is not None,
            rule_id=rule.id if rule else None,
            description=rule.description if rule else None,
        )
