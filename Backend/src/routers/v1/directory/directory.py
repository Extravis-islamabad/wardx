"""Directory router — LDAP / Active Directory sign-in settings and sync.

GET  /directory        — the configuration (null when none is saved)
PUT  /directory        — save the configuration (bind password is write-only)
POST /directory/test   — look up one user with the service account
POST /directory/sync   — run the sync now (dry run, or force past the disable limit)
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from src.contracts.dto.directory.directory_config_dto import DirectoryConfigDTO
from src.contracts.schemas.requests.directory.directory_requests import (
    DirectoryConfigIn,
    DirectoryTest,
    RoleMapping,
    SyncRequest,
)
from src.contracts.schemas.responses.common import (
    CONFLICT_RESPONSE,
    FORBIDDEN_RESPONSE,
    NOT_FOUND_RESPONSE,
    UNAUTHORIZED_RESPONSE,
    VALIDATION_ERROR_RESPONSE,
    APIResponse,
    ok,
)
from src.contracts.schemas.responses.directory.directory_responses import (
    DirectoryConfigResponse,
    DirectoryTestResultResponse,
    SyncResultResponse,
)
from src.core.permissions import DIRECTORY_MANAGE
from src.dependencies.auth import ActorDep, require_permission
from src.dependencies.directory import DirectoryServiceDep, DirectorySyncServiceDep

router = APIRouter(prefix="/directory", tags=["directory"])


def _to_response(dto: DirectoryConfigDTO) -> DirectoryConfigResponse:
    return DirectoryConfigResponse(
        enabled=dto.enabled,
        server_url=dto.server_url,
        start_tls=dto.start_tls,
        verify_tls=dto.verify_tls,
        ca_cert_pem=dto.ca_cert_pem,
        bind_dn=dto.bind_dn,
        has_bind_password=dto.has_bind_password,
        user_base_dn=dto.user_base_dn,
        user_filter=dto.user_filter,
        attr_username=dto.attr_username,
        attr_email=dto.attr_email,
        attr_full_name=dto.attr_full_name,
        group_base_dn=dto.group_base_dn,
        group_filter=dto.group_filter,
        role_mappings=[RoleMapping.model_validate(m) for m in dto.role_mappings],
        default_role=dto.default_role,
        timeout_seconds=dto.timeout_seconds,
        sync_interval_minutes=dto.sync_interval_minutes,
        sync_max_disable_percent=dto.sync_max_disable_percent,
        last_sync_at=dto.last_sync_at,
        last_sync_status=dto.last_sync_status,
        last_sync_summary=dto.last_sync_summary,
        updated_at=dto.updated_at,
    )


@router.get(
    "",
    response_model=APIResponse[DirectoryConfigResponse | None],
    dependencies=[Depends(require_permission(DIRECTORY_MANAGE))],
    summary="Get the directory configuration",
    responses={**UNAUTHORIZED_RESPONSE, **FORBIDDEN_RESPONSE},
)
async def get_config(service: DirectoryServiceDep) -> APIResponse[DirectoryConfigResponse | None]:
    cfg = await service.get_config()
    return ok(_to_response(cfg) if cfg else None)


@router.put(
    "",
    response_model=APIResponse[DirectoryConfigResponse],
    dependencies=[Depends(require_permission(DIRECTORY_MANAGE))],
    summary="Save the directory configuration",
    responses={
        **UNAUTHORIZED_RESPONSE,
        **FORBIDDEN_RESPONSE,
        **CONFLICT_RESPONSE,
        **VALIDATION_ERROR_RESPONSE,
    },
)
async def save_config(
    request: DirectoryConfigIn, service: DirectoryServiceDep, actor: ActorDep
) -> APIResponse[DirectoryConfigResponse]:
    values = request.model_dump(exclude={"bind_password"}, mode="json")
    cfg = await service.save_config(actor, values, request.bind_password or None)
    return ok(_to_response(cfg), "Directory settings saved")


@router.post(
    "/test",
    response_model=APIResponse[DirectoryTestResultResponse],
    dependencies=[Depends(require_permission(DIRECTORY_MANAGE))],
    summary="Look up one user in the directory",
    responses={
        **UNAUTHORIZED_RESPONSE,
        **FORBIDDEN_RESPONSE,
        **NOT_FOUND_RESPONSE,
        **VALIDATION_ERROR_RESPONSE,
    },
)
async def test_lookup(
    request: DirectoryTest, service: DirectoryServiceDep, actor: ActorDep
) -> APIResponse[DirectoryTestResultResponse]:
    user = await service.test_lookup(actor, request.username)
    return ok(
        DirectoryTestResultResponse(
            dn=user.dn,
            username=user.username,
            email=user.email,
            full_name=user.full_name,
            groups=list(user.groups),
            role=user.role,
        )
    )


@router.post(
    "/sync",
    response_model=APIResponse[SyncResultResponse],
    dependencies=[Depends(require_permission(DIRECTORY_MANAGE))],
    summary="Run the directory sync now",
    responses={
        **UNAUTHORIZED_RESPONSE,
        **FORBIDDEN_RESPONSE,
        **CONFLICT_RESPONSE,
        **VALIDATION_ERROR_RESPONSE,
    },
)
async def sync_now(
    request: SyncRequest, service: DirectorySyncServiceDep, actor: ActorDep
) -> APIResponse[SyncResultResponse]:
    result = await service.run_sync(actor=actor, dry_run=request.dry_run, force=request.force)
    return ok(SyncResultResponse(**result.summary()))
