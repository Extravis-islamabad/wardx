"""Gateway sessions need 'use' or 'retrieve' on the account's safe; 'use' never reveals."""

from __future__ import annotations

import asyncssh
import pytest

from tests.conftest import DEVICE_PASSWORD, DEVICE_USER
from tests.integration.safes_support import ALL_PERMS, checkout, grant, me, new_safe, tag

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def _connect(gateway, login: str, password: str) -> asyncssh.SSHClientConnection:
    return await asyncssh.connect(
        "127.0.0.1",
        gateway.port,
        username=login,
        password=password,
        known_hosts=None,
        client_keys=None,
        agent_path=None,
        config=None,
        preferred_auth="password",
    )


async def test_use_connects_without_retrieve_and_list_alone_is_refused(
    gateway, device, client, admin, make_user
):
    safe_id = await new_safe(client, admin)
    owner = await make_user(f"keeper{tag()}", role="admin")
    await grant(client, admin, safe_id, "user", (await me(client, owner))["id"], ALL_PERMS)
    target = (
        await client.post(
            "/targets",
            headers=owner,
            json={
                "name": f"safe-rtr-{tag()}",
                "address": "127.0.0.1",
                "port": device.port,
                "platform": "cisco_ios",
                "protocol": "ssh",
            },
        )
    ).json()["data"]
    account = (
        await client.post(
            "/accounts",
            headers=owner,
            json={
                "target_id": target["id"],
                "safe_id": safe_id,
                "username": DEVICE_USER,
                "secret": DEVICE_PASSWORD,
            },
        )
    ).json()["data"]

    user_name, lister_name = f"gwuse{tag()}", f"gwlist{tag()}"
    user, lister = await make_user(user_name), await make_user(lister_name)
    await grant(client, admin, safe_id, "user", (await me(client, user))["id"], ["list", "use"])
    await grant(client, admin, safe_id, "user", (await me(client, lister))["id"], ["list"])

    conn = await _connect(
        gateway, f"{user_name}%{DEVICE_USER}%{target['name']}", f"User-Passw0rd-{user_name}"
    )
    result = await conn.run("show version", timeout=5)
    assert "FakeOS 1.0" in result.stdout and result.exit_status == 0
    conn.close()
    # 'use' is not 'retrieve': no console check-out, so no reveal.
    assert (await checkout(client, user, account["id"])).status_code == 403

    conn = await _connect(
        gateway, f"{lister_name}%{DEVICE_USER}%{target['name']}", f"User-Passw0rd-{lister_name}"
    )
    result = await conn.run(timeout=5)
    assert result.exit_status == 1 and "needs 'use' or 'retrieve'" in result.stderr
    conn.close()

    # Not a member at all: the account does not exist for them.
    outsider_name = f"gwout{tag()}"
    await make_user(outsider_name)
    conn = await _connect(
        gateway,
        f"{outsider_name}%{DEVICE_USER}%{target['name']}",
        f"User-Passw0rd-{outsider_name}",
    )
    result = await conn.run(timeout=5)
    assert result.exit_status == 1 and f"No account '{DEVICE_USER}'" in result.stderr
    conn.close()
