"""Learning and changing a target's SSH host key (ROTATION.md §14, fix 4).

Two simulated SSH devices (tests/integration/fake_device.py) with different host keys
stand in for "the device" and "the device after its key changed". Nothing here sends a
credential to either: probing reads the key without authenticating.
"""

from __future__ import annotations

import pytest

from tests.integration.fake_device import FakeDevice
from tests.integration.rotation.fake_driver import PRESENTED_FINGERPRINT
from tests.integration.rotation.rotation_support import sql

pytestmark = pytest.mark.asyncio(loop_scope="session")


@pytest.fixture
async def devices():
    first, second = FakeDevice("nobody", "unused-1"), FakeDevice("nobody", "unused-2")
    await first.start()
    await second.start()
    yield first, second
    await first.stop()
    await second.stop()


def fp(device: FakeDevice) -> str:
    return device.host_key.get_fingerprint("sha256")


async def _ssh_target(rotlab, device: FakeDevice) -> dict:
    """A target pointing at a simulated SSH device, with no key pinned yet."""
    target = await rotlab.target()
    await sql(
        "UPDATE inventory.targets SET address = '127.0.0.1', port = :p, ssh_host_key = NULL, "
        "ssh_host_key_fingerprint = NULL WHERE id = :i",
        p=device.port,
        i=target["id"],
    )
    return target


async def _probe(rotlab, target_id: str, headers=None):
    return await rotlab.client.post(
        f"/targets/{target_id}/host-key/probe", headers=headers or rotlab.admin
    )


async def _accept(rotlab, target_id: str, fingerprint: str, headers=None):
    return await rotlab.client.post(
        f"/targets/{target_id}/host-key/accept",
        headers=headers or rotlab.admin,
        json={"fingerprint": fingerprint},
    )


async def _pinned(target_id: str) -> dict:
    return (
        await sql(
            "SELECT ssh_host_key_fingerprint, host_key_mismatch_at, "
            "host_key_mismatch_fingerprint FROM inventory.targets WHERE id = :i",
            i=target_id,
        )
    )[0]


async def test_probe_shows_the_fingerprint_and_pins_nothing(rotlab, devices):
    device, _ = devices
    target = await _ssh_target(rotlab, device)
    resp = await _probe(rotlab, target["id"])
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["presented_fingerprint"] == fp(device)
    assert data["presented_fingerprint"].startswith("SHA256:")
    assert data["key_type"] == "ssh-ed25519"
    assert data["pinned_fingerprint"] is None and data["matches_pin"] is False
    assert (await _pinned(target["id"]))["ssh_host_key_fingerprint"] is None
    assert device.logins == []  # nothing was sent


async def test_accept_pins_only_the_fingerprint_that_was_compared(rotlab, devices):
    device, _ = devices
    target = await _ssh_target(rotlab, device)
    wrong = "SHA256:" + "A" * 43
    resp = await _accept(rotlab, target["id"], wrong)
    assert resp.status_code == 409, resp.text
    assert resp.json()["error"]["details"]["presented_fingerprint"] == fp(device)
    assert (await _pinned(target["id"]))["ssh_host_key_fingerprint"] is None
    failed = await sql(
        "SELECT outcome FROM audit.events WHERE action = 'target.host_key_accept' "
        "AND object_id = :i",
        i=target["id"],
    )
    assert [f["outcome"] for f in failed] == ["failure"]

    resp = await _accept(rotlab, target["id"], fp(device))
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["ssh_host_key_fingerprint"] == fp(device)
    assert device.logins == []


async def test_learning_and_changing_are_audited_per_safe(rotlab, devices):
    device, changed = devices
    target = await _ssh_target(rotlab, device)
    safe_a, safe_b = await rotlab.safe(), await rotlab.safe()
    await rotlab.account(target=target, safe_id=safe_a, on_device=False)
    await rotlab.account(target=target, safe_id=safe_b, on_device=False)

    assert (await _accept(rotlab, target["id"], fp(device))).status_code == 200
    # The device's key changes; an administrator compares and re-learns it explicitly.
    await sql(
        "UPDATE inventory.targets SET port = :p WHERE id = :i", p=changed.port, i=target["id"]
    )
    probe = (await _probe(rotlab, target["id"])).json()["data"]
    assert probe["pinned_fingerprint"] == fp(device)
    assert probe["presented_fingerprint"] == fp(changed) and probe["matches_pin"] is False
    assert (await _accept(rotlab, target["id"], fp(changed))).status_code == 200

    events = await sql(
        "SELECT action, safe_id, details->>'previous_fingerprint' AS prev, "
        "details->>'fingerprint' AS fp FROM audit.events "
        "WHERE object_id = :i AND action IN ('target.host_key_learned', "
        "'target.host_key_changed') ORDER BY seq",
        i=target["id"],
    )
    learned = [e for e in events if e["action"] == "target.host_key_learned"]
    changed_ev = [e for e in events if e["action"] == "target.host_key_changed"]
    # One target-level event plus one per affected safe, for each change.
    assert sorted(str(e["safe_id"]) for e in learned) == sorted(["None", safe_a, safe_b])
    assert sorted(str(e["safe_id"]) for e in changed_ev) == sorted(["None", safe_a, safe_b])
    assert all(e["prev"] == fp(device) and e["fp"] == fp(changed) for e in changed_ev)


async def test_needs_manage_accounts_on_every_safe_of_the_target(rotlab, devices):
    device, _ = devices
    target = await _ssh_target(rotlab, device)
    # No accounts yet: inventory.manage alone is enough.
    assert (await _probe(rotlab, target["id"])).status_code == 200

    safe_a, safe_b = await rotlab.safe(), await rotlab.safe()
    await rotlab.account(target=target, safe_id=safe_a, on_device=False)
    await rotlab.account(target=target, safe_id=safe_b, on_device=False)
    # The admin role loses manage_accounts on one of the two safes.
    await sql(
        "UPDATE inventory.safe_members SET permissions = ARRAY['list','use','retrieve'] "
        "WHERE safe_id = :s AND principal_type = 'role' AND principal_key = 'admin'",
        s=safe_b,
    )
    for call in (
        _probe(rotlab, target["id"]),
        _accept(rotlab, target["id"], fp(device)),
        rotlab.client.post(f"/targets/{target['id']}/host-key/reset", headers=rotlab.admin),
    ):
        resp = await call
        assert resp.status_code == 403, resp.text
    assert (await _pinned(target["id"]))["ssh_host_key_fingerprint"] is None


async def test_changed_key_blocks_rotation_and_verify_until_accepted(rotlab, devices):
    device, _ = devices
    account = await rotlab.account()
    target_id = account["target"]["id"]

    # A rotation meets another key: the job fails, the target records the mismatch,
    # and one high alert is raised.
    rotlab.driver.fail("connect", "host_key")
    done = await rotlab.run((await rotlab.request(account["id"]))["id"])
    assert done["status"] == "failed", done
    state = await _pinned(target_id)
    assert state["host_key_mismatch_at"] is not None
    assert state["host_key_mismatch_fingerprint"] == PRESENTED_FINGERPRINT
    alerts = await sql(
        "SELECT severity FROM security.alerts WHERE kind = 'target.host_key_changed' "
        "AND object_id = :i",
        i=target_id,
    )
    assert [a["severity"] for a in alerts] == ["high"]

    # Every later rotation and verify is refused before any connection is made.
    connects = rotlab.driver.count("connect")
    for op in ("rotate", "verify"):
        job = await rotlab.run((await rotlab.request(account["id"], op))["id"])
        assert job["status"] in ("failed", "needs_attention"), job
        assert "host key" in (job["detail"] or "").lower()
    assert rotlab.driver.count("connect") == connects
    # Seeing the same presented key again doesn't raise another alert.
    assert (
        len(
            await sql(
                "SELECT 1 FROM security.alerts WHERE kind = 'target.host_key_changed' "
                "AND object_id = :i",
                i=target_id,
            )
        )
        == 1
    )

    # Only an explicit accept clears it; then rotation works again.
    await sql(
        "UPDATE inventory.targets SET address = '127.0.0.1', port = :p WHERE id = :i",
        p=device.port,
        i=target_id,
    )
    assert (await _accept(rotlab, target_id, fp(device))).status_code == 200
    cleared = await _pinned(target_id)
    assert cleared["host_key_mismatch_at"] is None
    assert cleared["ssh_host_key_fingerprint"] == fp(device)
    job = await rotlab.run((await rotlab.request(account["id"]))["id"])
    assert job["status"] == "succeeded", job


async def test_reset_does_not_clear_a_mismatch(rotlab, devices):
    """Never auto-accept: clearing the pin leaves rotation blocked until an explicit
    accept, even if a gateway session later pins a key on first use."""
    account = await rotlab.account()
    target_id = account["target"]["id"]
    rotlab.driver.fail("connect", "host_key")
    await rotlab.run((await rotlab.request(account["id"]))["id"])
    resp = await rotlab.client.post(f"/targets/{target_id}/host-key/reset", headers=rotlab.admin)
    assert resp.status_code == 200, resp.text
    assert (await _pinned(target_id))["host_key_mismatch_at"] is not None
    assert resp.json()["data"]["host_key_mismatch_fingerprint"] == PRESENTED_FINGERPRINT
