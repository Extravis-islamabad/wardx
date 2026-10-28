"""Permission codenames and which role holds which.

Routers gate on codenames (``require_permission("inventory.manage")``), never on
roles, the same way MonetX does. Roles are fixed bundles of codenames for now;
custom roles and per-safe grants plug in here later without touching routers.
"""

from __future__ import annotations

from src.core.enums import Role

INVENTORY_VIEW = "inventory.view"
INVENTORY_MANAGE = "inventory.manage"
ACCESS_USE = "access.use"
ACCESS_APPROVE = "access.approve"
# See every check-out, not only your own (approvers see every request via ACCESS_APPROVE).
ACCESS_VIEW_ALL = "access.view_all"
ACCESS_REVOKE = "access.revoke"
SESSIONS_VIEW_ALL = "sessions.view_all"
SESSIONS_TERMINATE = "sessions.terminate"
POLICY_VIEW = "policy.view"
POLICY_MANAGE = "policy.manage"
AUDIT_VIEW = "audit.view"
USERS_MANAGE = "users.manage"
DIRECTORY_MANAGE = "directory.manage"
DASHBOARD_VIEW = "dashboard.view"
# Your own profile: who am I, sign out, change password, your own MFA.
PROFILE_SELF = "profile.self"

_EVERYONE = frozenset({INVENTORY_VIEW, ACCESS_USE, POLICY_VIEW, DASHBOARD_VIEW, PROFILE_SELF})

ROLE_PERMISSIONS: dict[Role, frozenset[str]] = {
    Role.ADMIN: frozenset(
        {
            INVENTORY_VIEW,
            INVENTORY_MANAGE,
            ACCESS_USE,
            ACCESS_APPROVE,
            ACCESS_VIEW_ALL,
            ACCESS_REVOKE,
            SESSIONS_VIEW_ALL,
            SESSIONS_TERMINATE,
            POLICY_VIEW,
            POLICY_MANAGE,
            AUDIT_VIEW,
            USERS_MANAGE,
            DIRECTORY_MANAGE,
            DASHBOARD_VIEW,
            PROFILE_SELF,
        }
    ),
    Role.APPROVER: _EVERYONE | {ACCESS_APPROVE},
    Role.AUDITOR: _EVERYONE | {ACCESS_VIEW_ALL, SESSIONS_VIEW_ALL, AUDIT_VIEW},
    Role.USER: _EVERYONE,
}


def role_has(role: Role | str, codename: str) -> bool:
    return codename in ROLE_PERMISSIONS.get(Role(role), frozenset())
