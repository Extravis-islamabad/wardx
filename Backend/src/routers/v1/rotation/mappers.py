"""Response mappings shared by the rotation routers."""

from __future__ import annotations

from src.contracts.dto.rotation.rotation_dto import (
    RotationAccountDTO,
    RotationJobDTO,
    SafeRotationPolicyDTO,
)
from src.contracts.schemas.responses.rotation.rotation_responses import (
    RotationAccountBriefResponse,
    RotationJobResponse,
    RotationStepResponse,
    SafeRotationPolicyResponse,
)


def job_response(dto: RotationJobDTO) -> RotationJobResponse:
    return RotationJobResponse(
        id=dto.id,
        account_id=dto.account_id,
        account_username=dto.account_username,
        target_id=dto.target_id,
        target_name=dto.target_name,
        safe_id=dto.safe_id,
        reason=dto.reason,
        status=dto.status,
        requested_by=dto.requested_by,
        note=dto.note,
        dry_run=dto.dry_run,
        not_before=dto.not_before,
        attempts=dto.attempts,
        waiting_since=dto.waiting_since,
        release_alerted_at=dto.release_alerted_at,
        started_at=dto.started_at,
        finished_at=dto.finished_at,
        from_version=dto.from_version,
        candidate_version=dto.candidate_version,
        secret_versions_touched=dto.secret_versions_touched,
        driver=dto.driver,
        detail=dto.detail,
        verify_result=dto.verify_result,
        resolution=dto.resolution,
        resolution_note=dto.resolution_note,
        resolved_by=dto.resolved_by,
        resolved_at=dto.resolved_at,
        created_at=dto.created_at,
        steps=[
            RotationStepResponse(
                step=s.step,
                outcome=s.outcome,
                secret_version=s.secret_version,
                detail=s.detail,
                transcript=s.transcript,
                started_at=s.started_at,
                finished_at=s.finished_at,
                channel=s.channel,
            )
            for s in dto.steps
        ],
    )


def policy_response(dto: SafeRotationPolicyDTO) -> SafeRotationPolicyResponse:
    return SafeRotationPolicyResponse(**{"safe_id": dto.safe_id, **dto.audit_view()})


def account_brief(dto: RotationAccountDTO) -> RotationAccountBriefResponse:
    return RotationAccountBriefResponse(
        id=dto.id,
        username=dto.username,
        safe_id=dto.safe_id,
        sync_status=dto.sync_status,
        risk_flags=dto.risk_flags,
        last_verified_at=dto.last_verified_at,
        risk_accepted_by=dto.risk_accepted_by,
        risk_accepted_by_name=dto.risk_accepted_by_name,
        risk_accepted_at=dto.risk_accepted_at,
        risk_accepted_reason=dto.risk_accepted_reason,
    )
