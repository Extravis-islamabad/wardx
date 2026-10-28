"""Current-user, actor and permission dependencies."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from src.contracts.dto.identity.user_dto import UserDTO
from src.core.context import Actor
from src.core.enums import Role
from src.dependencies.database import SQLSessionDep
from src.dependencies.identity import AuthServiceDep, MfaServiceDep
from src.errors.exceptions import ForbiddenError, MfaEnrollmentRequired, UnauthorizedError

# Transitional alias; new code uses SQLSessionDep.
SessionDep = SQLSessionDep

_bearer = HTTPBearer(auto_error=False)


def client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


# What a user whose role requires MFA may still reach before enrolling.
_MFA_ENROLMENT_PATHS = ("/api/v1/auth/me", "/api/v1/auth/mfa", "/api/v1/auth/logout")


async def get_current_user(
    request: Request,
    auth: AuthServiceDep,
    mfa: MfaServiceDep,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> UserDTO:
    if credentials is None:
        raise UnauthorizedError("Not authenticated")
    user = await auth.current_user(credentials.credentials)
    if (
        mfa.is_required(user.role)
        and not request.url.path.startswith(_MFA_ENROLMENT_PATHS)
        and not await mfa.is_enabled(user.id)
    ):
        raise MfaEnrollmentRequired("Your role requires MFA. Set it up to continue.")
    return user


CurrentUserDep = Annotated[UserDTO, Depends(get_current_user)]


async def get_actor(user: CurrentUserDep, request: Request) -> Actor:
    return Actor(
        id=user.id, username=user.username, role=Role(user.role), source_ip=client_ip(request)
    )


ActorDep = Annotated[Actor, Depends(get_actor)]


def require_permission(*codenames: str):
    """Dependency factory: the actor, if their role holds ANY of the codenames.

    Use as ``dependencies=[Depends(require_permission("inventory.manage"))]`` and
    take ``ActorDep`` in the handler when it needs the actor; FastAPI resolves
    ``get_actor`` once per request.
    """

    async def _check(actor: ActorDep) -> Actor:
        if not any(actor.can(c) for c in codenames):
            raise ForbiddenError(f"Missing required permission: {', '.join(codenames)}")
        return actor

    return _check
