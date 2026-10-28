"""Safe health, break-glass coverage and the directory-outage warning.

Health of an active safe (break-glass never makes a safe healthy):
- ``healthy``: at least one direct user member (an active user) or role member (a
  role at least one active user holds);
- ``break_glass_only`` (warning): only directory groups (or nobody), but an eligible
  break-glass holder exists;
- ``unreachable`` (critical): only directory groups (or nobody), and no eligible
  break-glass holder.

Eligible break-glass holder: local, active, MFA-enrolled and holding access.emergency.
Fewer than two is flagged: one holder is a single point of failure (an MFA reset
revokes their grant).

While the directory is unreachable, the outage warning lists the active safes nobody
can reach once group memberships count as none. That is stricter than the health
check: only local users count, since directory users cannot sign in during the outage.
"""

from __future__ import annotations

from src.contracts.dto.safes.safe_health_dto import (
    BREAK_GLASS_ONLY,
    HEALTHY,
    UNREACHABLE,
    AttentionDTO,
    BreakGlassCoverageDTO,
    DirectoryStatusDTO,
    SafeHealthDTO,
    SafeMembershipSummaryDTO,
)
from src.repositories.directory.directory_config_repository import DirectoryConfigRepository
from src.repositories.safes.safe_health_repository import SafeHealthRepository
from src.services.identity.user_grant_service import UserGrantService


def _health(s: SafeMembershipSummaryDTO, state: str) -> SafeHealthDTO:
    return SafeHealthDTO(
        safe_id=s.safe_id,
        name=s.name,
        state=state,
        user_members=s.user_members,
        role_members=s.role_members,
        group_members=s.group_members,
    )


class SafeHealthService:
    def __init__(
        self,
        repo: SafeHealthRepository,
        directory: DirectoryConfigRepository,
        grants: UserGrantService,
    ) -> None:
        self._repo = repo
        self._directory = directory
        self._grants = grants

    async def break_glass(self) -> BreakGlassCoverageDTO:
        holders = await self._grants.holders()
        return BreakGlassCoverageDTO(
            eligible_holders=sum(h.eligible for h in holders), holders=len(holders)
        )

    async def safes(self, coverage: BreakGlassCoverageDTO | None = None) -> list[SafeHealthDTO]:
        coverage = coverage or await self.break_glass()
        fallback = BREAK_GLASS_ONLY if coverage.eligible_holders else UNREACHABLE
        return [
            _health(s, HEALTHY if s.user_members or s.role_members else fallback)
            for s in await self._repo.summaries()
        ]

    async def directory(self) -> DirectoryStatusDTO:
        cfg = await self._directory.get()
        if cfg is None or not cfg.enabled:
            return DirectoryStatusDTO(enabled=False, reachable=None, checked_at=None, error=None)
        affected: list[SafeHealthDTO] = []
        if cfg.reachable is False:
            affected = [
                _health(s, UNREACHABLE)
                for s in await self._repo.summaries()
                if not (s.local_user_members or s.local_role_members)
            ]
        return DirectoryStatusDTO(
            enabled=True,
            reachable=cfg.reachable,
            checked_at=cfg.reachability_checked_at,
            error=cfg.reachability_error,
            affected_safes=affected,
        )

    async def attention(self) -> AttentionDTO:
        coverage = await self.break_glass()
        return AttentionDTO(
            directory=await self.directory(),
            break_glass=coverage,
            safes=[s for s in await self.safes(coverage) if s.state != HEALTHY],
        )
