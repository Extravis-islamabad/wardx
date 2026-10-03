from __future__ import annotations

from fastapi import APIRouter

from src.contracts.schemas.common import APIResponse, ok
from src.contracts.schemas.directory import (
    DirectoryConfigIn,
    DirectoryConfigOut,
    DirectoryTest,
    DirectoryTestResult,
)
from src.dependencies.auth import AdminActor, SessionDep
from src.models import DirectoryConfig
from src.services import directory_service as svc

router = APIRouter(prefix="/directory", tags=["directory"])


def _out(cfg: DirectoryConfig) -> DirectoryConfigOut:
    return DirectoryConfigOut.model_validate(
        {
            **{c.key: getattr(cfg, c.key) for c in DirectoryConfig.__table__.columns},
            "has_bind_password": cfg.bind_secret_version is not None,
        }
    )


@router.get("", response_model=APIResponse[DirectoryConfigOut | None])
async def get_config(_: AdminActor, session: SessionDep):
    cfg = await svc.get_config(session)
    return ok(_out(cfg) if cfg else None)


@router.put("", response_model=APIResponse[DirectoryConfigOut])
async def save_config(body: DirectoryConfigIn, actor: AdminActor, session: SessionDep):
    values = body.model_dump(exclude={"bind_password"}, mode="json")
    cfg = await svc.save_config(session, actor, values, body.bind_password or None)
    return ok(_out(cfg), "Directory settings saved")


@router.post("/test", response_model=APIResponse[DirectoryTestResult])
async def test_lookup(body: DirectoryTest, actor: AdminActor, session: SessionDep):
    user = await svc.test_lookup(session, actor, body.username)
    return ok(
        DirectoryTestResult(
            dn=user.dn,
            username=user.username,
            email=user.email,
            full_name=user.full_name,
            groups=list(user.groups),
            role=user.role,
        )
    )
