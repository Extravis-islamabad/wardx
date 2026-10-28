"""Directory groups for safe membership, from the group cache.

- Local users belong to no directory group.
- A directory user's groups come from ``iam.user_group_cache``. When the entry is
  older than ``group_cache_minutes`` (WARDX_GROUP_CACHE_MINUTES, default 15), the
  groups are re-read through the directory's service-account lookup and cached again.
- **Fail closed:** when the directory is off, unreachable, or failed within the last
  ``directory_retry_seconds``, groups count as none and are reported unverified (a
  warning is logged). Direct and role memberships keep working.
- A user the directory no longer knows has no groups.

The refreshed cache is written on its own short session, so it is kept even when the
request that triggered the refresh fails or only reads.
"""

from __future__ import annotations

import uuid
from datetime import timedelta

import structlog

from src.core.config import Settings
from src.directory.ldap_client import DirectoryAuthFailed, normalise_dn
from src.errors.exceptions import AppError
from src.models import utcnow
from src.repositories.identity.group_cache_repository import GroupCacheRepository
from src.repositories.identity.user_repository import UserRepository
from src.services.directory.directory_service import DirectoryService, SideSessions

logger = structlog.get_logger(__name__)


class GroupMembershipService:
    def __init__(
        self,
        cache: GroupCacheRepository,
        users: UserRepository,
        directory: DirectoryService,
        settings: Settings,
        side_sessions: SideSessions | None = None,
    ) -> None:
        self._cache = cache
        self._users = users
        self._directory = directory
        self._settings = settings
        self._side_sessions = side_sessions

    async def groups_for(self, user_id: uuid.UUID) -> tuple[frozenset[str], bool]:
        """(normalised group DNs, verified). Unverified means the groups count as none."""
        user = await self._users.get(user_id)
        if user is None or user.auth_source != "ldap":
            return frozenset(), True
        cached = await self._cache.get(user_id)
        ttl = timedelta(minutes=self._settings.group_cache_minutes)
        if cached is not None and utcnow() - cached[1] < ttl:
            return cached[0], True

        if not await self._directory.is_enabled():
            logger.warning("group_cache_stale_directory_off", user=user.username)
            return frozenset(), False
        if await self._directory.recently_unreachable(self._settings.directory_retry_seconds):
            logger.warning("group_cache_stale_directory_down", user=user.username)
            return frozenset(), False
        try:
            found = await self._directory.lookup(user.username)
            groups = frozenset(normalise_dn(g) for g in found.groups)
        except DirectoryAuthFailed:
            groups = frozenset()  # no longer (uniquely) in the directory: no groups
        except AppError as exc:
            logger.warning("group_refresh_failed", user=user.username, error=exc.message)
            return frozenset(), False
        await self._store(user_id, groups)
        return groups, True

    async def _store(self, user_id: uuid.UUID, groups: frozenset[str]) -> None:
        if self._side_sessions is None:
            await self._cache.store(user_id, groups, utcnow())
            return
        async with self._side_sessions() as session:
            repo = GroupCacheRepository(session)
            await repo.store(user_id, groups, utcnow())
            await repo.commit()
