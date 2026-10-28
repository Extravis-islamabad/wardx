"""Shared helpers for the safes tests: safes, members, and accounts placed in them."""

from __future__ import annotations

import uuid

from httpx import AsyncClient

ALL_PERMS = [
    "list",
    "use",
    "retrieve",
    "manage_accounts",
    "manage_members",
    "view_audit",
    "approve",
]
SECRET = "Safe-Held-Secret-1"  # gitleaks:allow


def tag() -> str:
    return uuid.uuid4().hex[:8]


async def me(client: AsyncClient, headers: dict) -> dict:
    resp = await client.get("/auth/me", headers=headers)
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]


async def new_safe(client: AsyncClient, admin: dict, name: str | None = None) -> str:
    resp = await client.post("/safes", headers=admin, json={"name": name or f"safe-{tag()}"})
    assert resp.status_code == 201, resp.text
    return resp.json()["data"]["id"]


async def add_member(
    client: AsyncClient, headers: dict, safe_id: str, ptype: str, key: str, perms: list[str]
):
    return await client.post(
        f"/safes/{safe_id}/members",
        headers=headers,
        json={"principal_type": ptype, "principal_key": key, "permissions": perms},
    )


async def grant(client, headers, safe_id, ptype, key, perms) -> dict:
    resp = await add_member(client, headers, safe_id, ptype, key, perms)
    assert resp.status_code == 201, resp.text
    return resp.json()["data"]


async def new_account(client: AsyncClient, headers: dict, safe_id: str, **extra) -> dict:
    """A fresh target with one account in ``safe_id``, created by ``headers``."""
    target = await client.post(
        "/targets",
        headers=headers,
        json={"name": f"t-{tag()}", "address": "10.0.0.1", "platform": "linux", "protocol": "ssh"},
    )
    assert target.status_code == 201, target.text
    resp = await client.post(
        "/accounts",
        headers=headers,
        json={
            "target_id": target.json()["data"]["id"],
            "safe_id": safe_id,
            "username": "root",
            "secret": SECRET,
            **extra,
        },
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["data"]


async def checkout(client: AsyncClient, headers: dict, account_id: str):
    return await client.post(
        "/checkouts",
        headers=headers,
        json={"account_id": account_id, "reason": "safes test", "duration_minutes": 5},
    )
