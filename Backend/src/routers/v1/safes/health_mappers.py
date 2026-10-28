"""Response mappings for safe health, shared by the safes and dashboard routers."""

from __future__ import annotations

from src.contracts.dto.safes.safe_health_dto import (
    MIN_BREAK_GLASS_HOLDERS,
    AttentionDTO,
    BreakGlassCoverageDTO,
    SafeHealthDTO,
)
from src.contracts.schemas.responses.safes.safe_responses import (
    AttentionResponse,
    BreakGlassCoverageResponse,
    DirectoryStatusResponse,
    SafeHealthResponse,
)


def health_response(dto: SafeHealthDTO) -> SafeHealthResponse:
    return SafeHealthResponse(
        safe_id=dto.safe_id,
        name=dto.name,
        state=dto.state,
        severity=dto.severity,
        user_members=dto.user_members,
        role_members=dto.role_members,
        group_members=dto.group_members,
    )


def coverage_response(dto: BreakGlassCoverageDTO) -> BreakGlassCoverageResponse:
    message = None
    if dto.warning:
        n = dto.eligible_holders
        message = (
            f"{n} eligible break-glass holder{'s' if n != 1 else ''} (local, active, MFA "
            f"enrolled); at least {MIN_BREAK_GLASS_HOLDERS} are needed. "
            + (
                "Nobody can use break-glass."
                if n == 0
                else "One holder is a single point of failure: an MFA reset revokes the grant."
            )
        )
    return BreakGlassCoverageResponse(
        eligible_holders=dto.eligible_holders,
        holders=dto.holders,
        minimum=MIN_BREAK_GLASS_HOLDERS,
        warning=dto.warning,
        message=message,
    )


def attention_response(dto: AttentionDTO) -> AttentionResponse:
    d = dto.directory
    return AttentionResponse(
        directory=DirectoryStatusResponse(
            enabled=d.enabled,
            reachable=d.reachable,
            unreachable=d.unreachable,
            checked_at=d.checked_at,
            error=d.error,
            affected_safes=[health_response(s) for s in d.affected_safes],
        ),
        break_glass=coverage_response(dto.break_glass),
        safes_needing_attention=[health_response(s) for s in dto.safes],
    )
