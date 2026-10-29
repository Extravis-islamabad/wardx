"""Health router.

GET /health/ready     — readiness: database reachable and vault unsealed
GET /health/cluster   — scheduler leader, replication and sync state, DR lag, gateway nodes
"""

from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, Depends

from src.contracts.dto.health.cluster_dto import ClusterDTO
from src.contracts.schemas.responses.common import (
    FORBIDDEN_RESPONSE,
    UNAUTHORIZED_RESPONSE,
    APIResponse,
    ok,
)
from src.contracts.schemas.responses.health.cluster_responses import (
    ClusterResponse,
    ConditionResponse,
    DrResponse,
    GatewayNodeResponse,
    LeaderResponse,
    ReplicaResponse,
    ReplicationResponse,
)
from src.core.config import get_settings
from src.core.permissions import CLUSTER_VIEW
from src.dependencies.auth import require_permission
from src.dependencies.health import ClusterServiceDep, HealthServiceDep

router = APIRouter(prefix="/health", tags=["health"])


@router.get("/ready", response_model=APIResponse[dict], summary="Readiness probe")
async def ready(service: HealthServiceDep) -> APIResponse[dict]:
    return ok(await service.readiness())


def _to_response(dto: ClusterDTO) -> ClusterResponse:
    settings = get_settings()
    leader = dto.leader
    return ClusterResponse(
        node=dto.node,
        leader=LeaderResponse(**asdict(leader), fresh=dto.leader_fresh) if leader else None,
        replication=ReplicationResponse(
            in_recovery=dto.replication.in_recovery,
            sync_state=dto.replication.sync_state,
            expect_sync_standby=settings.ha_expect_sync_standby,
            replicas=[ReplicaResponse(**asdict(r)) for r in dto.replication.replicas],
            error=dto.replication.error,
        ),
        dr=DrResponse(
            site_configured=dto.dr.configured,
            replica_name=dto.dr.replica_name,
            state=dto.dr.state,
            lag_seconds=dto.dr.lag_seconds,
            max_lag_seconds=dto.dr.max_lag_seconds,
            reason=dto.dr.reason,
            rotation_paused=dto.dr.rotation_paused,
        ),
        dr_site_configured=dto.dr.configured,
        conditions=[
            ConditionResponse(
                kind=c.kind,
                active=c.active,
                since=c.since,
                checked_at=c.checked_at,
                details=c.details,
            )
            for c in dto.conditions
        ],
        gateways=[GatewayNodeResponse(**asdict(g)) for g in dto.gateways],
        gateway_host_keys_consistent=dto.gateway_host_keys_consistent,
    )


@router.get(
    "/cluster",
    response_model=APIResponse[ClusterResponse],
    dependencies=[Depends(require_permission(CLUSTER_VIEW))],
    summary="Cluster health: leader, replication, DR lag, gateway nodes",
    responses={**UNAUTHORIZED_RESPONSE, **FORBIDDEN_RESPONSE},
)
async def cluster(service: ClusterServiceDep) -> APIResponse[ClusterResponse]:
    return ok(_to_response(await service.overview(get_settings().node())))
