"""Brief mappings shared by the access repositories."""

from __future__ import annotations

from src.contracts.dto.access.access_request_dto import AccountBriefDTO, UserBriefDTO
from src.models import Account, User


def user_brief(user: User) -> UserBriefDTO:
    return UserBriefDTO(id=user.id, username=user.username, full_name=user.full_name)


def account_brief(account: Account) -> AccountBriefDTO:
    return AccountBriefDTO(
        id=account.id,
        username=account.username,
        target_id=account.target_id,
        target_name=account.target.name,
        target_address=account.target.address,
        safe_id=account.safe_id,
        safe_name=account.safe.name,
    )
