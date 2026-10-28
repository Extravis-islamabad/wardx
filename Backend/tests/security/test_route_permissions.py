"""Every API route is gated by a permission codename, or is on the reviewed public list.

The walk reads the dependency tree FastAPI actually executes for each route (the
effective route contexts, which include router-level dependencies), and finds the
codenames ``require_permission`` tagged onto its checker. A route added without a
gate fails here before it can ship.
"""

from __future__ import annotations

import uuid

import pytest
from fastapi.routing import APIRoute

from src.core.app_factory import create_app
from src.core.enums import Role
from src.core.permissions import (
    ALL_PERMISSIONS,
    APP_ONLY,
    DIRECT_GRANT_ONLY,
    PROVIDER_FETCH,
    ROLE_PERMISSIONS,
)

# Reachable without a codename. Changing this list is a security review item.
PUBLIC_ROUTES: frozenset[tuple[str, str]] = frozenset(
    {
        ("GET", "/health"),  # liveness, no data
        ("GET", "/api/v1/health/ready"),  # readiness: database reachable, vault unsealed
        ("POST", "/api/v1/auth/login"),
        ("POST", "/api/v1/auth/refresh"),  # proves possession of a refresh token instead
        ("POST", "/api/v1/auth/mfa/verify"),  # proves possession of an mfa token instead
        # Credential provider: authenticates by client credentials (client_id + secret),
        # IP allowlist and failed-attempt rate limits (docs/phase1/CREDENTIAL_PROVIDER.md §2).
        ("POST", "/api/v1/provider/token"),
    }
)

# Gated by an application token (get_current_app), never by a user's permissions.
APP_ROUTES_PREFIX = "/api/v1/provider/"


def _codenames(dependant) -> set[str]:
    found = set(getattr(dependant.call, "permission_codenames", ()) or ())
    for sub in dependant.dependencies:
        found |= _codenames(sub)
    return found


def _routes() -> list[tuple[str, str, set[str]]]:
    """(method, path, codenames) for every route the app serves."""
    out = []
    for route in create_app().routes:
        if type(route).__name__ == "_IncludedRouter":
            contexts = list(route.effective_route_contexts())
        elif isinstance(route, APIRoute):
            contexts = [route]
        else:
            continue  # starlette's own routes: docs, openapi
        for ctx in contexts:
            for method in ctx.methods:
                out.append((method, ctx.path, _codenames(ctx.dependant)))
    return out


ROUTES = _routes()


def test_walker_sees_the_whole_api():
    # Guards the guard: a walker that silently sees nothing would pass everything.
    paths = {path for _, path, _ in ROUTES}
    assert len(ROUTES) > 50
    assert "/api/v1/targets" in paths and "/api/v1/checkouts/{checkout_id}/reveal" in paths


def test_every_route_has_a_permission_codename():
    ungated = sorted(
        (method, path)
        for method, path, codes in ROUTES
        if not codes and (method, path) not in PUBLIC_ROUTES
    )
    assert ungated == [], f"routes without require_permission(...): {ungated}"


def test_public_list_has_no_stale_or_gated_entries():
    by_route = {(method, path): codes for method, path, codes in ROUTES}
    for entry in PUBLIC_ROUTES:
        assert entry in by_route, f"{entry} no longer exists; remove it from PUBLIC_ROUTES"
        assert not by_route[entry], f"{entry} is gated now; remove it from PUBLIC_ROUTES"


def test_every_codename_is_a_known_permission():
    # A typo in a codename would lock everyone out of a route.
    unknown = sorted({c for _, _, codes in ROUTES for c in codes} - ALL_PERMISSIONS)
    assert unknown == []


def test_admin_holds_everything_but_direct_grant_and_app_only_codenames():
    # Break-glass (access.emergency) is a per-user grant only: no role holds it. App-only
    # codenames (provider.fetch) are held by application identities only.
    assert ALL_PERMISSIONS - ROLE_PERMISSIONS[Role.ADMIN] == DIRECT_GRANT_ONLY | APP_ONLY
    for role in Role:
        assert not ROLE_PERMISSIONS[role] & (DIRECT_GRANT_ONLY | APP_ONLY)


def test_app_routes_and_only_app_routes_use_the_app_gate():
    """Provider routes are gated by provider.fetch alone (an app token); no user route
    accepts it, and no provider route accepts a user codename."""
    for method, path, codes in ROUTES:
        if (method, path) in PUBLIC_ROUTES:
            continue
        if path.startswith(APP_ROUTES_PREFIX):
            assert codes == {PROVIDER_FETCH}, (method, path, codes)
        else:
            assert PROVIDER_FETCH not in codes, (method, path, codes)


def test_users_never_hold_app_only_codenames():
    from src.core.context import Actor

    actor = Actor(id=None, username="x", role=Role.ADMIN, grants=frozenset(APP_ONLY))
    assert not any(actor.can(c) for c in APP_ONLY)


def _fill(path: str) -> str:
    """Path parameters replaced with a random UUID."""
    out, rest = "", path
    while "{" in rest:
        before, _, after = rest.partition("{")
        out += before + str(uuid.uuid4())
        rest = after.partition("}")[2]
    return out + rest


GATED = sorted((m, p) for m, p, codes in ROUTES if codes and p.startswith("/api/v1/"))


@pytest.mark.parametrize(("method", "path"), GATED, ids=[f"{m} {p}" for m, p in GATED])
async def test_gated_route_refuses_anonymous_callers(client, method, path):
    resp = await client.request(method, _fill(path).removeprefix("/api/v1"), json={})
    assert resp.status_code == 401, resp.text
    # Provider routes answer with the provider's own code (CREDENTIAL_PROVIDER.md §5).
    expected = "invalid_token" if path.startswith(APP_ROUTES_PREFIX) else "unauthorized"
    assert resp.json()["error"]["code"] == expected
