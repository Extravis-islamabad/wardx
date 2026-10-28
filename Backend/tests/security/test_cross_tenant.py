"""Cross-tenant isolation: tenant A's credentials never reach tenant B's data.

WardX is single-tenant until the tenancy step (Backend/TENANCY_KEYS.md, then the
tenancy build). These tests state the contract that step must satisfy, and are
skipped until the ``two_tenants`` fixture exists. The Phase 1 gate requires them
to run and pass: skipped does not count.

Contract, for every tenant-scoped resource (targets, accounts, secrets, requests,
check-outs, sessions, recordings, command rules, audit events, users, directory):
- A's token with B's real ids reads as 404, the same as an id that does not exist
  (no existence oracle), for GET, PATCH, PUT, DELETE and action POSTs.
- A's lists never contain B's rows, whatever the filters.
- Pointing ``X-Active-Tenant-Id`` at B without a platform grant is 403, and is audited.
- A secret sealed for B cannot be opened with A's tenant key (AAD and key both differ).
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.skip(
    reason="Tenancy not built yet; enable with the two_tenants fixture in the tenancy step"
)

RESOURCES = [
    ("GET", "/targets/{target_id}"),
    ("PATCH", "/targets/{target_id}"),
    ("DELETE", "/targets/{target_id}"),
    ("GET", "/accounts/{account_id}"),
    ("PUT", "/accounts/{account_id}/secret"),
    ("POST", "/checkouts/{checkout_id}/reveal"),
    ("POST", "/checkouts/{checkout_id}/checkin"),
    ("POST", "/requests/{request_id}/decision"),
    ("GET", "/sessions/{session_id}"),
    ("GET", "/sessions/{session_id}/recording"),
    ("POST", "/sessions/{session_id}/terminate"),
]


@pytest.mark.parametrize(("method", "path"), RESOURCES)
async def test_tenant_a_cannot_touch_tenant_b_by_id(two_tenants, method, path):
    a, b = two_tenants
    resp = await a.client.request(method, path.format(**b.ids), headers=a.admin, json={})
    assert resp.status_code == 404


async def test_tenant_a_lists_never_include_tenant_b_rows(two_tenants):
    a, b = two_tenants
    for path in ("/targets", "/accounts", "/checkouts", "/sessions", "/audit/events", "/users"):
        rows = (await a.client.get(path, headers=a.admin, params={"page_size": 200})).json()["data"]
        assert not {r["id"] for r in rows} & b.all_ids


async def test_active_tenant_header_cannot_switch_tenant(two_tenants):
    a, b = two_tenants
    headers = {**a.admin, "X-Active-Tenant-Id": b.tenant_id}
    assert (await a.client.get("/targets", headers=headers)).status_code == 403


async def test_secret_sealed_for_b_cannot_be_opened_with_a_key(two_tenants):
    a, b = two_tenants
    assert a.open_with_own_key(b.sealed_secret) is None
