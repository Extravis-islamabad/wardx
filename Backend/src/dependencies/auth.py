"""Session, current-user and role dependencies."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from src.core.config import get_settings, resolve_jwt_secret
from src.core.context import Actor
from src.core.enums import Role
from src.core.security import decode_token
from src.dependencies.database import SQLSessionDep
from src.errors.exceptions import ForbiddenError, MfaEnrollmentRequired, UnauthorizedError
from src.models import User
from src.services import mfa_service

# Transitional alias; new code uses SQLSessionDep.
SessionDep = SQLSessionDep

_bearer = HTTPBearer(auto_error=False)


def client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


# What a user whose role requires MFA may still reach before enrolling.
_MFA_ENROLMENT_PATHS = ("/api/v1/auth/me", "/api/v1/auth/mfa", "/api/v1/auth/logout")


async def get_current_user(
    request: Request,
    session: SessionDep,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> User:
    if credentials is None:
        raise UnauthorizedError("Not authenticated")
    claims = decode_token(
        credentials.credentials, secret=resolve_jwt_secret(get_settings()), expected_type="access"
    )
    try:
        user_id = uuid.UUID(claims["sub"])
    except ValueError as exc:
        raise UnauthorizedError("Invalid token") from exc
    user = await session.get(User, user_id)
    if user is None or not user.is_active or user.token_version != claims["tv"]:
        raise UnauthorizedError("Session is no longer valid")
    settings = get_settings()
    if (
        mfa_service.is_required(settings, user.role)
        and not request.url.path.startswith(_MFA_ENROLMENT_PATHS)
        and not await mfa_service.is_enabled(session, user.id)
    ):
        raise MfaEnrollmentRequired("Your role requires MFA. Set it up to continue.")
    return user


CurrentUserDep = Annotated[User, Depends(get_current_user)]
CurrentUser = CurrentUserDep


async def get_actor(user: CurrentUser, request: Request) -> Actor:
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


def require_roles(*roles: Role):
    async def _check(actor: ActorDep) -> Actor:
        if not actor.has_role(*roles):
            raise ForbiddenError("Your role does not allow this action")
        return actor

    return _check


AdminActor = Annotated[Actor, Depends(require_roles(Role.ADMIN))]
ApproverActor = Annotated[Actor, Depends(require_roles(Role.ADMIN, Role.APPROVER))]
AuditReader = Annotated[Actor, Depends(require_roles(Role.ADMIN, Role.AUDITOR))]
