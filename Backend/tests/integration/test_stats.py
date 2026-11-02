"""Per-page KPI endpoints (GET /<resource>/stats).

The database is shared by the whole session, so these check invariants rather than
absolute numbers: a stats total equals its list's total for the same actor, counts are
scoped exactly like the list, counters move with the rows they count, and each stats
route needs the same permission as its list.
"""

from __future__ import annotations

import pytest

from tests.integration.safes_support import ALL_PERMS, grant, me, new_account, new_safe, tag

pytestmark = pytest.mark.asyncio(loop_scope="session")

# (stats endpoint, the list it summarises)
PAIRS = [
    ("/accounts/stats", "/accounts"),
    ("/targets/stats", "/targets"),
    ("/safes/stats", "/safes"),
    ("/users/stats", "/users"),
    ("/apps/stats", "/apps"),
    ("/checkouts/stats", "/checkouts"),
    ("/requests/stats", "/requests"),
    ("/sessions/stats", "/sessions"),
    ("/rotation/jobs/stats", "/rotation/jobs"),
    ("/audit/stats", "/audit/events"),
]


async def _stats(client, headers, url: str) -> dict:
    resp = await client.get(url, headers=headers)
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]


async def _total(client, headers, url: str) -> int:
    resp = await client.get(url, headers=headers, params={"page_size": 1})
    assert resp.status_code == 200, resp.text
    return resp.json()["total"]


@pytest.mark.parametrize(("stats_url", "list_url"), PAIRS)
async def test_stats_total_matches_the_list(client, admin, stats_url, list_url):
    stats = await _stats(client, admin, stats_url)
    assert stats["total"] == await _total(client, admin, list_url)


async def test_status_breakdowns_add_up(client, admin):
    jobs = await _stats(client, admin, "/rotation/jobs/stats")
    assert sum(jobs["by_status"].values()) == jobs["total"]
    checkouts = await _stats(client, admin, "/checkouts/stats")
    parts = ("active", "returned", "expired", "revoked")
    assert sum(checkouts[k] for k in parts) == checkouts["total"]
    sessions = await _stats(client, admin, "/sessions/stats")
    parts = ("active", "closed", "terminated", "failed")
    assert sum(sessions[k] for k in parts) == sessions["total"]
    requests = await _stats(client, admin, "/requests/stats")
    parts = ("pending", "approved", "used", "denied", "expired", "cancelled")
    assert sum(requests[k] for k in parts) == requests["total"]


async def test_account_stats_are_scoped_like_the_list(client, admin, make_user):
    safe_id = await new_safe(client, admin)
    keeper = await make_user(f"sk{tag()}", role="admin")
    await grant(client, admin, safe_id, "user", (await me(client, keeper))["id"], ALL_PERMS)
    await new_account(client, keeper, safe_id)
    await new_account(client, keeper, safe_id)

    # Other tests may give every user some safes (role grants), so measure the change
    # this one grant makes rather than absolute numbers.
    lister = await make_user(f"sl{tag()}")
    accounts_before = await _stats(client, lister, "/accounts/stats")
    safes_before = await _stats(client, lister, "/safes/stats")
    await grant(client, admin, safe_id, "user", (await me(client, lister))["id"], ["list"])

    lister_stats = await _stats(client, lister, "/accounts/stats")
    assert lister_stats["total"] == await _total(client, lister, "/accounts")
    assert lister_stats["total"] == accounts_before["total"] + 2
    # A user who was not granted the safe does not see its accounts counted.
    outsider = await make_user(f"so{tag()}")
    outsider_stats = await _stats(client, outsider, "/accounts/stats")
    assert outsider_stats["total"] == await _total(client, outsider, "/accounts")
    assert outsider_stats["total"] == accounts_before["total"]

    lister_safes = await _stats(client, lister, "/safes/stats")
    assert lister_safes["total"] == await _total(client, lister, "/safes")
    assert lister_safes["total"] == safes_before["total"] + 1
    assert lister_safes["accounts"] == safes_before["accounts"] + 2
    # Safe health is for safes.manage only.
    assert lister_safes["break_glass_only"] is None and lister_safes["unreachable"] is None
    admin_safes = await _stats(client, admin, "/safes/stats")
    assert admin_safes["break_glass_only"] is not None


async def test_account_counters_move_with_the_rows(client, admin, make_user):
    safe_id = await new_safe(client, admin)
    keeper = await make_user(f"sm{tag()}", role="admin")
    await grant(client, admin, safe_id, "user", (await me(client, keeper))["id"], ALL_PERMS)
    before = await _stats(client, keeper, "/accounts/stats")
    # exclusive_checkout defaults to on: one exclusive account without a secret,
    # one shared account with a secret.
    await new_account(client, keeper, safe_id, secret=None)
    await new_account(client, keeper, safe_id, exclusive_checkout=False)
    after = await _stats(client, keeper, "/accounts/stats")
    assert after["total"] == before["total"] + 2
    assert after["without_secret"] == before["without_secret"] + 1
    assert after["exclusive"] == before["exclusive"] + 1


async def test_target_and_user_counters(client, admin, make_user):
    targets = await _stats(client, admin, "/targets/stats")
    assert targets["active"] + targets["inactive"] == targets["total"]
    before = await _stats(client, admin, "/users/stats")
    await make_user(f"su{tag()}", role="approver")
    after = await _stats(client, admin, "/users/stats")
    assert (after["total"], after["approvers"]) == (before["total"] + 1, before["approvers"] + 1)
    assert after["active"] + after["disabled"] == after["total"]


async def test_audit_stats_count_sign_ins(client, admin, make_user):
    before = await _stats(client, admin, "/audit/stats")
    await make_user(f"sa{tag()}")  # signs in once
    after = await _stats(client, admin, "/audit/stats")
    assert after["logins_24h"] == before["logins_24h"] + 1
    assert after["last_24h"] > before["last_24h"]


@pytest.mark.parametrize("url", ["/users/stats", "/apps/stats", "/audit/stats"])
async def test_stats_need_the_lists_permission(client, make_user, url):
    user = await make_user(f"sp{tag()}")
    assert (await client.get(url, headers=user)).status_code == 403
