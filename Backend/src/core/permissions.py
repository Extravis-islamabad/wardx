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
# Approvers by role. Deciding a request is decided per safe (approve) and level; this
# codename stays for role bundles and the console.
# See every check-out (and every request), not only your own.
ACCESS_VIEW_ALL = "access.view_all"
ACCESS_REVOKE = "access.revoke"
SESSIONS_VIEW_ALL = "sessions.view_all"
SESSIONS_TERMINATE = "sessions.terminate"
# Read command rules and use the rule tester (the tester can probe the rules). The gateway
# applies rules server-side, so connecting needs no read permission. Replaces the retired
# policy.view, which every role held.
COMMANDS_VIEW = "commands.view"
POLICY_MANAGE = "policy.manage"
AUDIT_VIEW = "audit.view"
USERS_MANAGE = "users.manage"
DIRECTORY_MANAGE = "directory.manage"
DASHBOARD_VIEW = "dashboard.view"
# Create and edit safes, and manage the members of any safe. Grants no access to the
# accounts inside: list, use and retrieve need safe membership (separation of duties).
SAFES_MANAGE = "safes.manage"
# Acknowledge security alerts (reading them needs AUDIT_VIEW).
ALERTS_ACKNOWLEDGE = "alerts.acknowledge"
# Break-glass: reveal any account regardless of safe membership, with a reason, audited
# and alerted. No role holds it: only a direct per-user grant (iam.user_permissions) to
# a local, MFA-enrolled user.
ACCESS_EMERGENCY = "access.emergency"
# Your own profile: who am I, sign out, change password, your own MFA.
PROFILE_SELF = "profile.self"
# Create and manage application identities (the credential provider's clients).
APPS_MANAGE = "apps.manage"
# Fetch a credential through the provider API. Held only by application identities
# (through a token from /provider/token), never by a user, role or grant.
PROVIDER_FETCH = "provider.fetch"

_EVERYONE = frozenset({INVENTORY_VIEW, ACCESS_USE, DASHBOARD_VIEW, PROFILE_SELF})

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
            COMMANDS_VIEW,
            POLICY_MANAGE,
            AUDIT_VIEW,
            USERS_MANAGE,
            DIRECTORY_MANAGE,
            SAFES_MANAGE,
            ALERTS_ACKNOWLEDGE,
            DASHBOARD_VIEW,
            PROFILE_SELF,
            APPS_MANAGE,
        }
    ),
    Role.APPROVER: _EVERYONE | {ACCESS_APPROVE},
    Role.AUDITOR: _EVERYONE | {ACCESS_VIEW_ALL, SESSIONS_VIEW_ALL, AUDIT_VIEW, COMMANDS_VIEW},
    Role.USER: _EVERYONE,
}


def role_has(role: Role | str, codename: str) -> bool:
    return codename in ROLE_PERMISSIONS.get(Role(role), frozenset())


# Codenames only ever held through a direct user grant, never through a role.
DIRECT_GRANT_ONLY = frozenset({ACCESS_EMERGENCY})
# Codenames only application identities hold: no role or user grant ever includes them.
APP_ONLY = frozenset({PROVIDER_FETCH})
# Every codename that exists (routes may only gate on these).
ALL_PERMISSIONS: frozenset[str] = ROLE_PERMISSIONS[Role.ADMIN] | DIRECT_GRANT_ONLY | APP_ONLY
# What a user can hold at all (a role bundle or a direct grant).
USER_PERMISSIONS: frozenset[str] = ALL_PERMISSIONS - APP_ONLY


def effective_permissions(role: Role | str, grants: frozenset[str] = frozenset()) -> frozenset[str]:
    """The role's bundle plus the user's direct grants (never an app-only codename)."""
    return ROLE_PERMISSIONS.get(Role(role), frozenset()) | (grants & USER_PERMISSIONS)
