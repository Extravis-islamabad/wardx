"""Shared setup for approval-workflow tests: a safe with a policy, its people, an account."""

from __future__ import annotations

from sqlalchemy import text

from src.core.db import session_factory
from tests.integration.safes_support import ALL_PERMS, grant, me, new_account, new_safe, tag

REQUESTER_PERMS = ["list", "retrieve", "use"]
APPROVER_PERMS = ["list", "approve"]


async def person(client, make_user, admin, safe_id: str, perms: list[str], role: str = "user"):
    """A new user who is a direct member of the safe; returns {headers, user}."""
    headers = await make_user(f"p{tag()}", role=role)
    user = await me(client, headers)
    await grant(client, admin, safe_id, "user", user["id"], perms)
    return {"headers": headers, "user": user}


async def set_policy(client, admin, safe_id: str, **policy):
    body = {"approval_required": True, **policy}
    resp = await client.put(f"/safes/{safe_id}/policy", headers=admin, json=body)
    return resp


async def approval_safe(client, admin, make_user, levels=None, **policy) -> dict:
    """A safe requiring approval (one level of one safe approver unless given), with a
    keeper (all permissions) and one account in it."""
    safe_id = await new_safe(client, admin)
    keeper = await person(client, make_user, admin, safe_id, ALL_PERMS, role="admin")
    account = await new_account(client, keeper["headers"], safe_id)
    if levels is not None or policy:
        resp = await set_policy(
            client, admin, safe_id, levels=levels or [{"required_approvals": 1}], **policy
        )
        assert resp.status_code == 200, resp.text
    return {"safe_id": safe_id, "keeper": keeper, "account": account}


async def request_access(client, headers, account_id: str, ticket: str | None = None):
    body = {"account_id": account_id, "reason": "maintenance window", "duration_minutes": 15}
    if ticket is not None:
        body["ticket_ref"] = ticket
    return await client.post("/requests", headers=headers, json=body)


async def decide(client, headers, request_id: str, approve: bool = True):
    return await client.post(
        f"/requests/{request_id}/decision", headers=headers, json={"approve": approve}
    )


async def notifications(client, headers) -> list[dict]:
    resp = await client.get("/notifications", headers=headers, params={"page_size": 100})
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]


async def kinds_for(client, headers, request_id: str) -> list[str]:
    return sorted(
        n["kind"] for n in await notifications(client, headers) if n["object_id"] == request_id
    )


async def run_sql(sql: str, **params) -> None:
    async with session_factory()() as s:
        await s.execute(text(sql), params)
        await s.commit()


async def sweep() -> dict:
    from src.dependencies.access import build_checkout_service

    async with session_factory()() as s:
        return await build_checkout_service(s).expire_overdue()
