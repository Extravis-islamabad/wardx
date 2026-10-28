"""MFA end to end: enrolment, two-step login, replay, recovery codes, policy, gateway."""

from __future__ import annotations

import asyncio
from urllib.parse import parse_qs, urlparse

import asyncssh
import pytest

from src.core import totp
from src.core.config import get_settings
from tests.conftest import DEVICE_USER, login

pytestmark = pytest.mark.asyncio(loop_scope="session")


def _now_step() -> int:
    return totp.current_step()


async def _enrol(client, headers) -> tuple[str, list[str], dict]:
    """Turn MFA on for the user; returns (seed, recovery codes, fresh headers)."""
    setup = (await client.post("/auth/mfa/setup", headers=headers)).json()["data"]
    seed = parse_qs(urlparse(setup["otpauth_uri"]).query)["secret"][0]
    assert seed == setup["secret"]
    resp = await client.post(
        "/auth/mfa/enable", headers=headers, json={"code": totp.code_at(seed, _now_step())}
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    fresh = {"Authorization": f"Bearer {data['tokens']['access_token']}"}
    return seed, data["recovery_codes"], fresh


async def _password_step(client, username: str, password: str) -> str:
    resp = await client.post("/auth/login", json={"username": username, "password": password})
    data = resp.json()["data"]
    assert data["mfa_required"] is True and data["access_token"] is None
    return data["mfa_token"]


async def test_enrol_then_login_needs_a_fresh_code(client, make_user):
    old = await make_user("mfa1")
    seed, recovery, fresh = await _enrol(client, old)

    # Enabling MFA signs out tokens that never proved a second factor; the fresh ones work.
    assert (await client.get("/auth/me", headers=old)).status_code == 401
    assert (await client.get("/auth/me", headers=fresh)).status_code == 200

    token = await _password_step(client, "mfa1", "User-Passw0rd-mfa1")
    # The code used to enable MFA cannot be replayed.
    replay = await client.post(
        "/auth/mfa/verify", json={"mfa_token": token, "code": totp.code_at(seed, _now_step())}
    )
    assert replay.status_code == 401
    ok = await client.post(
        "/auth/mfa/verify",
        json={"mfa_token": token, "code": totp.code_at(seed, _now_step() + 1)},
    )
    assert ok.status_code == 200 and ok.json()["data"]["access_token"]

    # Recovery codes work once each.
    token = await _password_step(client, "mfa1", "User-Passw0rd-mfa1")
    first = await client.post("/auth/mfa/verify", json={"mfa_token": token, "code": recovery[0]})
    assert first.status_code == 200
    token = await _password_step(client, "mfa1", "User-Passw0rd-mfa1")
    again = await client.post("/auth/mfa/verify", json={"mfa_token": token, "code": recovery[0]})
    assert again.status_code == 401

    status = (await client.get("/auth/mfa", headers=fresh)).json()["data"]
    assert status == {
        "enabled": True,
        "pending": False,
        "required": False,
        "recovery_codes_left": 9,
    }


async def test_mfa_token_is_not_an_access_token(client, make_user):
    headers = await make_user("mfa2")
    await _enrol(client, headers)
    token = await _password_step(client, "mfa2", "User-Passw0rd-mfa2")
    resp = await client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 401


async def test_wrong_codes_count_towards_lockout(client, make_user):
    headers = await make_user("mfa3")
    await _enrol(client, headers)
    token = await _password_step(client, "mfa3", "User-Passw0rd-mfa3")
    for _ in range(5):
        resp = await client.post("/auth/mfa/verify", json={"mfa_token": token, "code": "000000"})
        assert resp.status_code in (401, 423)
    resp = await client.post(
        "/auth/login", json={"username": "mfa3", "password": "User-Passw0rd-mfa3"}
    )
    assert resp.status_code == 423


async def test_role_policy_blocks_until_enrolled(client, admin, make_user):
    settings = get_settings()
    settings.mfa_required_roles = ["auditor"]
    try:
        headers = await make_user("aud-mfa", role="auditor")
        resp = await client.post(
            "/auth/login", json={"username": "aud-mfa", "password": "User-Passw0rd-aud-mfa"}
        )
        assert resp.json()["data"]["mfa_enrollment_required"] is True
        blocked = await client.get("/audit/events", headers=headers)
        assert blocked.status_code == 403
        assert blocked.json()["error"]["code"] == "mfa_enrollment_required"
        assert (await client.get("/auth/mfa", headers=headers)).json()["data"]["required"] is True

        _, _, fresh = await _enrol(client, headers)
        assert (await client.get("/audit/events", headers=fresh)).status_code == 200
        # A required role cannot switch MFA off.
        resp = await client.post("/auth/mfa/disable", headers=fresh, json={"code": "123456"})
        assert resp.status_code == 409
    finally:
        settings.mfa_required_roles = []


async def test_admin_reset_removes_mfa(client, admin, make_user):
    headers = await make_user("mfa4")
    await _enrol(client, headers)
    me = (await client.get("/users", headers=admin, params={"search": "mfa4"})).json()["data"][0]
    assert (await client.post(f"/users/{me['id']}/mfa/reset", headers=admin)).status_code == 200
    # Password alone signs in again.
    assert await login(client, "mfa4", "User-Passw0rd-mfa4")


# ── Gateway ──


class _CodeClient(asyncssh.SSHClient):
    """Answers the gateway's keyboard-interactive prompts: password, then code."""

    def __init__(self, password: str, code: str) -> None:
        self.password, self.code, self.prompts = password, code, []

    def kbdint_auth_requested(self) -> str:
        return ""

    def kbdint_challenge_received(self, name, instructions, lang, prompts):
        self.prompts += [p for p, _ in prompts]
        return [self.code if "code" in p.lower() else self.password for p, _ in prompts]


async def _gateway_connect(gateway, user: str, client_factory):
    return await asyncssh.connect(
        "127.0.0.1",
        gateway.port,
        username=f"{user}%{DEVICE_USER}%fake-rtr",
        known_hosts=None,
        client_keys=None,
        agent_path=None,
        config=None,
        client_factory=client_factory,
        preferred_auth="keyboard-interactive,password",
    )


async def test_gateway_asks_for_the_code(client, make_user, gateway, lab):
    headers = await make_user("mfa-ssh")
    seed, _, _ = await _enrol(client, headers)

    # Password only (no code): refused.
    with pytest.raises(asyncssh.PermissionDenied):
        await asyncssh.connect(
            "127.0.0.1",
            gateway.port,
            username=f"mfa-ssh%{DEVICE_USER}%fake-rtr",
            password="User-Passw0rd-mfa-ssh",
            known_hosts=None,
            client_keys=None,
            agent_path=None,
            config=None,
            preferred_auth="password",
        )

    holder = {}

    def factory():
        holder["c"] = _CodeClient("User-Passw0rd-mfa-ssh", totp.code_at(seed, _now_step() + 1))
        return holder["c"]

    conn = await _gateway_connect(gateway, "mfa-ssh", factory)
    result = await conn.run("show version", timeout=5)
    conn.close()
    assert "FakeOS" in result.stdout
    assert holder["c"].prompts == ["WardX password: ", "Authenticator or recovery code: "]

    # A wrong code is refused, and a client that keeps retrying is cut off
    # after MAX_AUTH_TRIES instead of hanging until the login timeout.
    started = asyncio.get_running_loop().time()
    with pytest.raises(asyncssh.PermissionDenied):
        await _gateway_connect(
            gateway, "mfa-ssh", lambda: _CodeClient("User-Passw0rd-mfa-ssh", "000000")
        )
    assert asyncio.get_running_loop().time() - started < 10
