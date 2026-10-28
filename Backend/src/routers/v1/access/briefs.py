"""Brief mappings shared by the access routers."""

from __future__ import annotations

from src.contracts.dto.access.access_request_dto import AccountBriefDTO, UserBriefDTO
from src.contracts.schemas.responses.access.access_request_responses import (
    AccountBriefResponse,
    UserBriefResponse,
)


def user_brief_response(dto: UserBriefDTO) -> UserBriefResponse:
    return UserBriefResponse(id=dto.id, username=dto.username, full_name=dto.full_name)


def account_brief_response(dto: AccountBriefDTO) -> AccountBriefResponse:
    return AccountBriefResponse(
        id=dto.id,
        username=dto.username,
        target_id=dto.target_id,
        target_name=dto.target_name,
        target_address=dto.target_address,
    )
