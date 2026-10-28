"""API v1 routers, aggregated into ``api_router`` (mounted at /api/v1 by the app factory)."""

from fastapi import APIRouter

from src.routers.v1.access import checkouts, emergency, requests
from src.routers.v1.audit import audit_events
from src.routers.v1.dashboard import dashboard
from src.routers.v1.directory import directory
from src.routers.v1.health import health
from src.routers.v1.identity import auth, mfa, users
from src.routers.v1.inventory import accounts, targets
from src.routers.v1.notify import notifications
from src.routers.v1.safes import audit as safe_audit
from src.routers.v1.safes import members, policy, safes
from src.routers.v1.security import alerts
from src.routers.v1.sessions import command_rules, gateway, sessions

api_router = APIRouter()

for _module in (
    health,
    auth,
    mfa,
    users,
    targets,
    accounts,
    safes,
    members,
    policy,
    safe_audit,
    notifications,
    requests,
    checkouts,
    emergency,
    alerts,
    audit_events,
    dashboard,
    gateway,
    sessions,
    command_rules,
    directory,
):
    api_router.include_router(_module.router)
