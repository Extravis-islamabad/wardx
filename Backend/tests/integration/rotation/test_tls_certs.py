"""API-SSL certificate pins and the MikroTik driver against simulated devices (ROTATION.md §15).

A simulated RouterOS: an SSH server (tests/integration/fake_device.py) for the host key
and the SSH verify fallback, plus a local TLS server speaking the API
(tests/tls_support.py) with a certificate generated for this run. The CHR lab tests
(test_mikrotik_lab.py) repeat the device-facing parts against a real RouterOS.
"""

from __future__ import annotations

import socket

import pytest

from src.rotation.drivers.registry import default_registry
from tests.integration.fake_device import FakeDevice
from tests.integration.rotation.rotation_support import Lab, sql, tag
from tests.tls_support import ApiServer, make_cert

pytestmark = pytest.mark.asyncio(loop_scope="session")

USER = "wardx_rot_sim"
START = "Sim-Start-Passw0rd-1"  # gitleaks:allow - a test-only value for a simulated device


class SimLab(Lab):
    def __init__(self, client, admin, ssh: FakeDevice, api: ApiServer) -> None:
        super().__init__(client, admin)
        self.registry = default_registry()
        self.ssh, self.api = ssh, api

    async def mikrotik_target(self, *, pin_ssh=True, pin_tls=True, **extra) -> dict:
        resp = await self.client.post(
            "/targets",
            headers=self.admin,
            json={
                "name": f"sim-rtr-{tag()}",
                "address": "127.0.0.1",
                "port": self.ssh.port,
                "platform": "mikrotik_routeros",
                "protocol": "ssh",
                "rotation_allowed": True,
                "api_port": self.api.port,
                **extra,
            },
        )
        assert resp.status_code == 201, resp.text
        target = resp.json()["data"]
        if pin_ssh:
            fp = self.ssh.host_key.get_fingerprint("sha256")
            r = await self.post(f"/targets/{target['id']}/host-key/accept", fingerprint=fp)
            assert r.status_code == 200, r.text
        if pin_tls:
            r = await self.post(
                f"/targets/{target['id']}/tls-cert/accept", fingerprint=self.api.cert.fingerprint
            )
            assert r.status_code == 200, r.text
            target = r.json()["data"]
        return target

    async def post(self, path: str, headers=None, **body):
        return await self.client.post(path, headers=headers or self.admin, json=body or None)


@pytest.fixture
async def sim(rotlab):
    ssh = FakeDevice(USER, START)
    await ssh.start()
    api = await ApiServer(make_cert("sim-rtr"), users={USER: START}).start()
    yield SimLab(rotlab.client, rotlab.admin, ssh, api)
    await api.stop()
    await ssh.stop()


async def _pins(target_id: str) -> dict:
    return (
        await sql(
            "SELECT tls_cert_fingerprint, tls_cert_mismatch_at, tls_cert_mismatch_fingerprint "
            "FROM inventory.targets WHERE id = :i",
            i=target_id,
        )
    )[0]


async def test_probe_shows_the_certificate_and_pins_nothing(sim):
    target = await sim.mikrotik_target(pin_tls=False)
    resp = await sim.post(f"/targets/{target['id']}/tls-cert/probe")
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["presented_fingerprint"] == sim.api.cert.fingerprint
    assert data["subject"] == "CN=sim-rtr" and data["not_after"]
    assert data["pinned_fingerprint"] is None and data["matches_pin"] is False
    assert (await _pins(target["id"]))["tls_cert_fingerprint"] is None
    assert sim.api.received == []  # the handshake only: no API word, no credential


async def test_accept_pins_only_the_compared_fingerprint(sim):
    target = await sim.mikrotik_target(pin_tls=False)
    wrong = make_cert("someone-else").fingerprint
    resp = await sim.post(f"/targets/{target['id']}/tls-cert/accept", fingerprint=wrong)
    assert resp.status_code == 409, resp.text
    assert resp.json()["error"]["details"]["presented_fingerprint"] == sim.api.cert.fingerprint
    failed = await sql(
        "SELECT outcome FROM audit.events WHERE action = 'target.tls_cert_accept' "
        "AND object_id = :i",
        i=target["id"],
    )
    assert [f["outcome"] for f in failed] == ["failure"]
    bad = await sim.post(f"/targets/{target['id']}/tls-cert/accept", fingerprint="SHA256:abc")
    assert bad.status_code == 422
    # RouterOS prints the fingerprint as 64 lower-case hex digits: accepted as written.
    routeros = sim.api.cert.fingerprint.replace(":", "").lower()
    resp = await sim.post(f"/targets/{target['id']}/tls-cert/accept", fingerprint=routeros)
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["tls_cert_fingerprint"] == sim.api.cert.fingerprint
    again = await sim.post(f"/targets/{target['id']}/tls-cert/accept", fingerprint=routeros)
    assert again.status_code == 409  # already pinned
    assert sim.api.received == []


async def test_learning_and_changing_are_audited_per_safe(sim, rotlab):
    target = await sim.mikrotik_target(pin_tls=False)
    safe_a, safe_b = await rotlab.safe(), await rotlab.safe()
    await rotlab.account(target=target, safe_id=safe_a, on_device=False)
    await rotlab.account(target=target, safe_id=safe_b, on_device=False)
    first = sim.api.cert.fingerprint
    assert (
        await sim.post(f"/targets/{target['id']}/tls-cert/accept", fingerprint=first)
    ).is_success
    other = await ApiServer(make_cert("sim-rtr-new"), users=sim.api.users).start()
    try:
        await sql(
            "UPDATE inventory.targets SET api_port = :p WHERE id = :i", p=other.port, i=target["id"]
        )
        new = other.cert.fingerprint
        resp = await sim.post(f"/targets/{target['id']}/tls-cert/accept", fingerprint=new)
        assert resp.status_code == 200, resp.text
    finally:
        await other.stop()
    events = await sql(
        "SELECT action, safe_id, details->>'previous_fingerprint' AS prev, "
        "details->>'fingerprint' AS fp FROM audit.events WHERE object_id = :i AND action IN "
        "('target.tls_cert_learned', 'target.tls_cert_changed') ORDER BY seq",
        i=target["id"],
    )
    for action in ("target.tls_cert_learned", "target.tls_cert_changed"):
        rows = [e for e in events if e["action"] == action]
        assert sorted(str(e["safe_id"]) for e in rows) == sorted(["None", safe_a, safe_b])
    assert all(e["prev"] == first and e["fp"] == new for e in events if "changed" in e["action"])


async def test_needs_manage_accounts_on_every_safe(sim, rotlab):
    target = await sim.mikrotik_target(pin_tls=False)
    safe_a, safe_b = await rotlab.safe(), await rotlab.safe()
    await rotlab.account(target=target, safe_id=safe_a, on_device=False)
    await rotlab.account(target=target, safe_id=safe_b, on_device=False)
    await sql(
        "UPDATE inventory.safe_members SET permissions = ARRAY['list','use','retrieve'] "
        "WHERE safe_id = :s AND principal_type = 'role' AND principal_key = 'admin'",
        s=safe_b,
    )
    tid = target["id"]
    for path, body in (
        (f"/targets/{tid}/tls-cert/probe", {}),
        (f"/targets/{tid}/tls-cert/accept", {"fingerprint": sim.api.cert.fingerprint}),
        (f"/targets/{tid}/tls-cert/reset", {}),
    ):
        resp = await sim.post(path, **body)
        assert resp.status_code == 403, resp.text
    assert (await _pins(tid))["tls_cert_fingerprint"] is None


async def test_rotation_over_api_ssl_records_the_channel(sim):
    target = await sim.mikrotik_target()
    account = await sim.account(password=START, target=target, username=USER, on_device=False)
    done = await sim.run((await sim.request(account["id"]))["id"])
    assert done["status"] == "succeeded", done
    assert done["verify_result"] == "verified"
    new = await sim.current(account["id"])
    assert sim.api.users[USER] == new != START
    channels = {s["step"]: s["channel"] for s in done["steps"]}
    assert channels["change"] == "api-ssl" and channels["verify"] == "api-ssl"
    assert channels["verify_negative"] == "api-ssl"
    assert sim.ssh.logins == []  # SSH was never logged into: only its host key was read
    for step in done["steps"]:
        for text in (step["transcript"] or "", step["detail"] or ""):
            assert new not in text and START not in text
    change = next(s for s in done["steps"] if s["step"] == "change")
    assert "/password =old-password=**** =new-password=****" in change["transcript"]


async def test_changed_certificate_blocks_until_accepted(sim):
    target = await sim.mikrotik_target()
    account = await sim.account(password=START, target=target, username=USER, on_device=False)
    impostor = await ApiServer(make_cert("impostor"), users=sim.api.users).start()
    try:
        await sql(
            "UPDATE inventory.targets SET api_port = :p WHERE id = :i",
            p=impostor.port,
            i=target["id"],
        )
        done = await sim.run((await sim.request(account["id"]))["id"])
        assert done["status"] == "failed", done
        assert "CERTIFICATE MISMATCH" in done["detail"]
        pins = await _pins(target["id"])
        assert pins["tls_cert_mismatch_at"] is not None
        assert pins["tls_cert_mismatch_fingerprint"] == impostor.cert.fingerprint
        alerts = await sql(
            "SELECT severity FROM security.alerts WHERE kind = 'target.tls_cert_changed' "
            "AND object_id = :i",
            i=target["id"],
        )
        assert [a["severity"] for a in alerts] == ["high"]
        assert impostor.received == [] and sim.ssh.logins == []  # nothing sent anywhere

        # Every later rotation and verify is refused before connecting.
        seen = impostor.connections
        for op in ("rotate", "verify"):
            job = await sim.run((await sim.request(account["id"], op))["id"])
            assert job["status"] == "failed" and "certificate" in job["detail"].lower(), job
        assert impostor.connections == seen and sim.ssh.logins == []

        # Reset clears the pin, never the mismatch.
        reset = await sim.post(f"/targets/{target['id']}/tls-cert/reset")
        assert reset.status_code == 200, reset.text
        assert (await _pins(target["id"]))["tls_cert_mismatch_at"] is not None

        # Only an explicit accept unblocks it.
        fp = impostor.cert.fingerprint
        assert (
            await sim.post(f"/targets/{target['id']}/tls-cert/accept", fingerprint=fp)
        ).is_success
        assert (await _pins(target["id"]))["tls_cert_mismatch_at"] is None
        done = await sim.run((await sim.request(account["id"]))["id"])
        assert done["status"] == "succeeded", done
    finally:
        await impostor.stop()


async def test_learn_the_device_identity_first(sim):
    for pins in ({"pin_tls": False}, {"pin_ssh": False}):
        target = await sim.mikrotik_target(**pins)
        account = await sim.account(password=START, target=target, username=USER, on_device=False)
        for op in ("rotate", "verify"):
            resp = await sim.post(
                f"/accounts/{account['id']}/{op}", reason="identity test", headers=sim.admin
            )
            assert resp.status_code == 409, resp.text
            assert "learn the device identity first" in resp.json()["error"]["message"]
    assert sim.api.received == [] and sim.ssh.logins == []


async def test_a_pin_cleared_after_queueing_is_refused_by_the_engine(sim):
    target = await sim.mikrotik_target()
    account = await sim.account(password=START, target=target, username=USER, on_device=False)
    job = await sim.request(account["id"])
    await sim.post(f"/targets/{target['id']}/tls-cert/reset")
    done = await sim.run(job["id"])
    assert done["status"] == "failed" and "learn the device identity first" in done["detail"]
    assert sim.api.received == [] and sim.ssh.logins == []


async def test_cleartext_api_only_is_non_rotatable(sim):
    target = await sim.mikrotik_target(pin_tls=False, api_tls=False)
    assert target["non_rotatable_reason"] == "non-rotatable (cleartext API)"
    account = await sim.account(password=START, target=target, username=USER, on_device=False)
    resp = await sim.post(f"/accounts/{account['id']}/rotate", reason="cleartext test")
    assert resp.status_code == 409 and "cleartext API" in resp.json()["error"]["message"]
    probe = await sim.post(f"/targets/{target['id']}/tls-cert/probe")
    assert probe.status_code == 409
    assert sim.api.received == [] and sim.ssh.logins == []


async def test_only_tls_platforms_have_a_certificate_pin(sim, rotlab):
    target = await rotlab.target()  # the fake 'generic' platform (SSH only)
    resp = await sim.post(f"/targets/{target['id']}/tls-cert/probe")
    assert resp.status_code == 409, resp.text


async def test_api_ssl_off_needs_attention_and_never_changes_over_ssh(sim):
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        closed = s.getsockname()[1]
    target = await sim.mikrotik_target()
    account = await sim.account(password=START, target=target, username=USER, on_device=False)
    await sql("UPDATE inventory.targets SET api_port = :p WHERE id = :i", p=closed, i=target["id"])
    done = await sim.run((await sim.request(account["id"]))["id"])
    assert done["status"] == "needs_attention", done
    assert done["detail"] == "API-SSL not enabled on device"
    assert sim.ssh.logins == [] and sim.ssh.executed == []
    assert sim.api.users[USER] == START
    await sql(
        "UPDATE access.rotation_jobs SET status = 'resolved', resolution = 'keep_current' "
        "WHERE id = :i",
        i=done["id"],
    )
    # Verify falls back to ONE SSH login per check (positive, then the negative one).
    done = await sim.run((await sim.request(account["id"], "verify"))["id"])
    assert done["status"] == "succeeded", done
    steps = {s["step"]: s for s in done["steps"]}
    assert steps["verify"]["channel"] == "ssh" and steps["verify_negative"]["channel"] == "ssh"
    assert "API-SSL not enabled on device" in steps["verify"]["detail"]
    assert [u for u, _ in sim.ssh.logins] == [USER, USER]
