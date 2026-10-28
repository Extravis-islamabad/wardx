"""The MikroTik driver against the CHR lab (ROTATION.md §15).

Runs against ``wardx-lab-mikrotik`` (lab/README.md); skipped, with the reason, when
Docker, the container or its API-SSL is not available. Every account is a ``wardx_rot_*``
user created here and removed afterwards; ``admin`` is only used to manage them, and the
api-ssl service and certificate are always restored (mikrotik_lab.py).
"""

from __future__ import annotations

import pytest

from src.core.config import get_settings
from src.rotation.drivers import ssh_login
from src.rotation.drivers.registry import default_registry
from src.transport import routeros_api
from tests.integration.rotation.mikrotik_lab import (
    API_PORT,
    API_SSL_PORT,
    HOST,
    SSH_PORT,
    Chr,
    new_password,
    requires_chr,
)
from tests.integration.rotation.rotation_support import Lab, sql, tag

pytestmark = [pytest.mark.asyncio(loop_scope="session"), requires_chr]


@pytest.fixture(scope="module")
async def chr_box():
    box = await Chr.connect()
    try:
        yield box
    finally:
        try:
            await box.remove_all()
            await box.restore()
            await box.check_restored()
            assert not [u for u in await box.users() if u.startswith("wardx_rot_")]
        finally:
            await box.close()


class Spy:
    """Counts what the MikroTik driver sends: SSH connections (host-key reads and logins)
    and API logins. The driver reaches both only through these module attributes."""

    def __init__(self, monkeypatch) -> None:
        self.ssh_key_reads = 0
        self.ssh_logins = 0
        self.api_logins = 0
        real_read, real_login, real_api = (
            ssh_login.presented_fingerprint,
            ssh_login.ssh_login,
            routeros_api.login,
        )

        async def read(*a, **k):
            self.ssh_key_reads += 1
            return await real_read(*a, **k)

        async def login(*a, **k):
            self.ssh_logins += 1
            return await real_login(*a, **k)

        async def api_login(*a, **k):
            self.api_logins += 1
            return await real_api(*a, **k)

        monkeypatch.setattr(ssh_login, "presented_fingerprint", read)
        monkeypatch.setattr(ssh_login, "ssh_login", login)
        monkeypatch.setattr(routeros_api, "login", api_login)

    @property
    def ssh(self) -> int:
        return self.ssh_key_reads + self.ssh_logins


class ChrLab(Lab):
    """The real MikroTik driver (default registry) against the CHR."""

    def __init__(self, client, admin, box: Chr) -> None:
        super().__init__(client, admin)
        self.registry = default_registry()
        self.box = box

    async def post(self, path: str, **body):
        return await self.client.post(path, headers=self.admin, json=body or None)

    async def mikrotik_target(self, *, pin_ssh=True, pin_tls=True, **extra) -> dict:
        resp = await self.client.post(
            "/targets",
            headers=self.admin,
            json={
                "name": f"lab-chr-{tag()}",
                "address": HOST,
                "port": SSH_PORT,
                "platform": "mikrotik_routeros",
                "protocol": "ssh",
                "rotation_allowed": True,
                "api_port": API_SSL_PORT,
                **extra,
            },
        )
        assert resp.status_code == 201, resp.text
        target = resp.json()["data"]
        # Read each identity (nothing sent), then accept exactly what was shown.
        for kind, on in (("host-key", pin_ssh), ("tls-cert", pin_tls)):
            if not on:
                continue
            probe = await self.post(f"/targets/{target['id']}/{kind}/probe")
            assert probe.status_code == 200, probe.text
            fp = probe.json()["data"]["presented_fingerprint"]
            accept = await self.post(f"/targets/{target['id']}/{kind}/accept", fingerprint=fp)
            assert accept.status_code == 200, accept.text
            target = accept.json()["data"]
        return target

    async def chr_account(self, purpose: str, *, group="read", target=None, safe_id=None):
        """A new wardx_rot_* user on the CHR and its WardX account (same password)."""
        name, password = await self.box.add_user(purpose, group)
        account = await self.account(
            password=password,
            target=target or await self.mikrotik_target(),
            username=name,
            safe_id=safe_id,
            on_device=False,
        )
        return {**account, "device_password": password}


@pytest.fixture
async def chr_lab(client, admin, chr_box):
    settings = get_settings()
    settings.rotation_enabled = True
    yield ChrLab(client, admin, chr_box)
    settings.rotation_enabled = False


def _clean(done: dict, *secrets: str) -> None:
    for step in done["steps"]:
        for text in (step["transcript"] or "", step["detail"] or ""):
            assert all(s not in text for s in secrets)


async def test_pinned_certificate_is_the_one_the_device_reports(chr_lab, chr_box):
    target = await chr_lab.mikrotik_target(pin_tls=False)
    probe = (await chr_lab.post(f"/targets/{target['id']}/tls-cert/probe")).json()["data"]
    on_device = await chr_box.device_fingerprint()  # RouterOS spelling: lower-case, no colons
    assert probe["presented_fingerprint"].replace(":", "").lower() == on_device
    resp = await chr_lab.post(f"/targets/{target['id']}/tls-cert/accept", fingerprint=on_device)
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["tls_cert_fingerprint"] == probe["presented_fingerprint"]


async def test_self_change_via_api_ssl(chr_lab, chr_box, monkeypatch):
    account = await chr_lab.chr_account("self")
    old = account["device_password"]
    spy = Spy(monkeypatch)
    done = await chr_lab.run((await chr_lab.request(account["id"]))["id"])
    assert done["status"] == "succeeded", done
    assert done["verify_result"] == "verified"
    new = await chr_lab.current(account["id"])
    assert new != old
    assert await chr_box.login_works(account["username"], new)
    assert not await chr_box.login_works(account["username"], old)
    steps = {s["step"]: s for s in done["steps"]}
    assert steps["change"]["channel"] == "api-ssl"
    assert "/password =old-password=**** =new-password=****" in steps["change"]["transcript"]
    assert steps["verify"]["channel"] == steps["verify_negative"]["channel"] == "api-ssl"
    assert spy.ssh_logins == 0  # SSH was only used to compare the host key
    _clean(done, old, new)
    device_text = await chr_box.history_and_log()
    assert old not in device_text and new not in device_text


async def test_reconcile_via_an_api_ssl_reconcile_account(chr_lab, chr_box, client, admin):
    target = await chr_lab.mikrotik_target()
    rec = await chr_lab.chr_account("rec", group="full", target=target)
    account = await chr_lab.chr_account("drift", target=target)
    resp = await client.patch(
        f"/accounts/{account['id']}", headers=admin, json={"reconcile_account_id": rec["id"]}
    )
    assert resp.status_code == 200, resp.text
    drifted = new_password()
    await chr_box.set_password(account["username"], drifted)  # behind WardX's back
    done = await chr_lab.run((await chr_lab.request(account["id"], "reconcile"))["id"])
    assert done["status"] == "succeeded", done
    reconcile = next(s for s in done["steps"] if s["step"] == "reconcile")
    assert reconcile["channel"] == "api-ssl" and "/user/set" in reconcile["transcript"]
    new = await chr_lab.current(account["id"])
    assert await chr_box.login_works(account["username"], new)
    assert (await chr_lab.state(account["id"]))["sync_status"] == "in_sync"
    used = await sql(
        "SELECT 1 FROM audit.events WHERE action = 'rotation.reconcile_account_used' "
        "AND object_id = :o",
        o=rec["id"],
    )
    assert len(used) == 1
    _clean(done, new, drifted, rec["device_password"])


async def test_verify_in_sync_then_out_of_sync(chr_lab, chr_box):
    account = await chr_lab.chr_account("sync")
    done = await chr_lab.run((await chr_lab.request(account["id"], "verify"))["id"])
    assert done["status"] == "succeeded" and done["verify_result"] == "verified", done
    assert (await chr_lab.state(account["id"]))["sync_status"] == "in_sync"
    await chr_box.set_password(account["username"], new_password())
    done = await chr_lab.run((await chr_lab.request(account["id"], "verify"))["id"])
    assert done["status"] == "failed", done
    assert (await chr_lab.state(account["id"]))["sync_status"] == "out_of_sync"
    assert "rotation.out_of_sync" in await chr_lab.alerts(account["id"])
    probe = next(s for s in done["steps"] if s["step"] == "empty_password_probe")
    assert probe["outcome"] == "auth_failed" and probe["channel"] == "api-ssl"


async def test_changed_certificate_blocks_with_no_ssh_connection(chr_lab, chr_box, monkeypatch):
    account = await chr_lab.chr_account("cert")
    target_id = account["target"]["id"]
    async with chr_box.certificate_swapped() as presented:
        spy = Spy(monkeypatch)
        done = await chr_lab.run((await chr_lab.request(account["id"]))["id"])
        assert done["status"] == "failed", done
        assert "CERTIFICATE MISMATCH" in done["detail"]
        assert spy.ssh == 0, "an SSH connection was attempted"
        assert spy.api_logins == 0, "a credential was sent"
        verify = await chr_lab.run((await chr_lab.request(account["id"], "verify"))["id"])
        assert verify["status"] == "failed" and "certificate" in verify["detail"].lower()
        assert spy.ssh == 0 and spy.api_logins == 0
    row = (
        await sql(
            "SELECT tls_cert_mismatch_fingerprint AS fp FROM inventory.targets WHERE id = :i",
            i=target_id,
        )
    )[0]
    assert row["fp"] == presented
    alerts = await sql(
        "SELECT severity FROM security.alerts WHERE kind = 'target.tls_cert_changed' "
        "AND object_id = :i",
        i=target_id,
    )
    assert [a["severity"] for a in alerts] == ["high"]
    # The device presents the pinned certificate again, but the recorded mismatch still
    # blocks until an administrator accepts explicitly.
    blocked = await chr_lab.run((await chr_lab.request(account["id"], "verify"))["id"])
    assert blocked["status"] == "failed" and "certificate" in blocked["detail"].lower()
    assert await chr_box.login_works(account["username"], account["device_password"])


async def test_api_ssl_disabled_needs_attention_and_no_ssh_change(chr_lab, chr_box, monkeypatch):
    account = await chr_lab.chr_account("nossl")
    async with chr_box.api_ssl_disabled():
        spy = Spy(monkeypatch)
        done = await chr_lab.run((await chr_lab.request(account["id"]))["id"])
        assert done["status"] == "needs_attention", done
        assert done["detail"] == "API-SSL not enabled on device"
        assert spy.ssh == 0 and spy.api_logins == 0  # nothing sent, no SSH fallback
        await sql(
            "UPDATE access.rotation_jobs SET status = 'resolved', resolution = 'keep_current' "
            "WHERE id = :i",
            i=done["id"],
        )
        # Verify is the one place SSH is used: one login, then the one wrong attempt.
        verify = await chr_lab.run((await chr_lab.request(account["id"], "verify"))["id"])
        assert verify["status"] == "succeeded" and verify["verify_result"] == "verified", verify
        steps = {s["step"]: s for s in verify["steps"]}
        assert steps["verify"]["channel"] == steps["verify_negative"]["channel"] == "ssh"
        assert spy.ssh_logins == 2
    assert await chr_box.login_works(account["username"], account["device_password"])


async def test_plain_api_is_refused(chr_lab, chr_box, monkeypatch):
    # Declared cleartext-only: vaultable, never rotated.
    target = await chr_lab.mikrotik_target(pin_tls=False, api_tls=False, api_port=API_PORT)
    assert target["non_rotatable_reason"] == "non-rotatable (cleartext API)"
    account = await chr_lab.chr_account("plain", target=target)
    spy = Spy(monkeypatch)
    resp = await chr_lab.post(f"/accounts/{account['id']}/rotate", reason="plain api test")
    assert resp.status_code == 409 and "cleartext API" in resp.json()["error"]["message"]
    # Pointed at the plain API port by mistake: TLS fails, so nothing is sent in clear.
    tls_target = await chr_lab.mikrotik_target()
    other = await chr_lab.chr_account("plainport", target=tls_target)
    await sql(
        "UPDATE inventory.targets SET api_port = :p WHERE id = :i", p=API_PORT, i=tls_target["id"]
    )
    done = await chr_lab.run((await chr_lab.request(other["id"]))["id"])
    assert done["status"] == "needs_attention" and done["detail"] == "API-SSL not enabled on device"
    assert spy.api_logins == 0 and spy.ssh == 0
    assert await chr_box.login_works(other["username"], other["device_password"])


async def test_missing_either_pin_is_refused(chr_lab, monkeypatch):
    spy = Spy(monkeypatch)
    for pins in ({"pin_tls": False}, {"pin_ssh": False}):
        target = await chr_lab.mikrotik_target(**pins)
        account = await chr_lab.chr_account("nopin", target=target)
        resp = await chr_lab.post(f"/accounts/{account['id']}/rotate", reason="pin test")
        assert resp.status_code == 409, resp.text
        assert "learn the device identity first" in resp.json()["error"]["message"]
    assert spy.api_logins == 0 and spy.ssh == 0


async def test_ssh_host_key_mismatch_blocks(chr_lab, chr_box, monkeypatch):
    import asyncssh

    account = await chr_lab.chr_account("hostkey")
    target_id = account["target"]["id"]
    other = asyncssh.generate_private_key("ssh-ed25519")
    await sql(
        "UPDATE inventory.targets SET ssh_host_key = :k, ssh_host_key_fingerprint = :f "
        "WHERE id = :i",
        k=other.export_public_key("openssh").decode().strip(),
        f=other.get_fingerprint("sha256"),
        i=target_id,
    )
    spy = Spy(monkeypatch)
    done = await chr_lab.run((await chr_lab.request(account["id"]))["id"])
    assert done["status"] == "failed" and "HOST KEY MISMATCH" in done["detail"], done
    assert spy.api_logins == 0  # no credential went over API-SSL either
    row = (
        await sql(
            "SELECT host_key_mismatch_fingerprint AS fp FROM inventory.targets WHERE id = :i",
            i=target_id,
        )
    )[0]
    assert row["fp"] == chr_box.host_key.get_fingerprint("sha256")
    kinds = await sql(
        "SELECT kind FROM security.alerts WHERE kind = 'target.host_key_changed' "
        "AND object_id = :i",
        i=target_id,
    )
    assert len(kinds) == 1
    assert await chr_box.login_works(account["username"], account["device_password"])


async def test_empty_password_account_is_detected(chr_lab, chr_box):
    name, _ = await chr_box.add_user("empty", password="")
    try:
        account = await chr_lab.account(
            password=new_password(),
            target=await chr_lab.mikrotik_target(),
            username=name,
            on_device=False,
        )
        done = await chr_lab.run((await chr_lab.request(account["id"], "verify"))["id"])
        assert done["status"] == "failed", done
        assert "empty password" in done["detail"]
        probe = next(s for s in done["steps"] if s["step"] == "empty_password_probe")
        assert probe["outcome"] == "ok" and probe["channel"] == "api-ssl"
        state = await chr_lab.state(account["id"])
        assert "high_risk_empty_password" in state["risk_flags"]
        assert "account.high_risk_empty_password" in await chr_lab.alerts(account["id"])
    finally:
        await chr_box.remove_user(name)
    assert name not in await chr_box.users()
