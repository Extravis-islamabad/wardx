"""The single directory configuration row (iam.directory_config, id 1)."""

from __future__ import annotations

from typing import Any

from src.contracts.dto.directory.directory_config_dto import DirectoryConfigDTO
from src.models import DirectoryConfig
from src.repositories.base import BaseRepository

_ID = 1


def _to_dto(row: DirectoryConfig) -> DirectoryConfigDTO:
    return DirectoryConfigDTO(
        enabled=row.enabled,
        server_url=row.server_url,
        start_tls=row.start_tls,
        verify_tls=row.verify_tls,
        ca_cert_pem=row.ca_cert_pem,
        bind_dn=row.bind_dn,
        bind_secret_version=row.bind_secret_version,
        user_base_dn=row.user_base_dn,
        user_filter=row.user_filter,
        attr_username=row.attr_username,
        attr_email=row.attr_email,
        attr_full_name=row.attr_full_name,
        group_base_dn=row.group_base_dn,
        group_filter=row.group_filter,
        role_mappings=list(row.role_mappings or []),
        default_role=row.default_role,
        timeout_seconds=row.timeout_seconds,
        sync_interval_minutes=row.sync_interval_minutes,
        sync_max_disable_percent=row.sync_max_disable_percent,
        last_sync_at=row.last_sync_at,
        last_sync_status=row.last_sync_status,
        last_sync_summary=row.last_sync_summary,
        updated_by=row.updated_by,
        updated_at=row.updated_at,
    )


class DirectoryConfigRepository(BaseRepository):
    async def get(self, *, lock: bool = False) -> DirectoryConfigDTO | None:
        row = await self._session.get(DirectoryConfig, _ID, with_for_update=lock or None)
        return _to_dto(row) if row else None

    async def save(self, values: dict[str, Any]) -> DirectoryConfigDTO:
        """Create the row with ``values``, or apply them to the existing one."""
        row = await self._session.get(DirectoryConfig, _ID)
        if row is None:
            row = DirectoryConfig(id=_ID, **values)
            self._session.add(row)
        else:
            for key, value in values.items():
                setattr(row, key, value)
        await self._session.flush()
        return _to_dto(row)
