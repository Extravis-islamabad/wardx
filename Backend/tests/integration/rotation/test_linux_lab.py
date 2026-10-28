"""The Linux driver end to end against throwaway lab containers (ROTATION.md §9).

Each test module run starts its own ``wardx-lab-linux-*`` container with its own
``wardx_rot_*`` users and removes it afterwards. Skipped, with the reason, when Docker
or the lab image is not available.
"""

from __future__ import annotations

import pytest

from src.core.config import get_settings
from src.rotation.drivers.registry import default_registry
from tests.integration.rotation.linux_lab import requires_docker, start_container
from tests.integration.rotation.rotation_support import CrashAt, Lab, tag

pytestmark = [pytest.mark.asyncio(loop_scope="session"), requires_docker]

USERS = [
    "wardx_rot_self",
    "wardx_rot_rec",
    "wardx_rot_admin",
    "wardx_rot_sync",
    "wardx_rot_crash",
    "wardx_rot_off",
]


@pytest.fixture(scope="module")
async def box():
    container = await start_container(USERS, sudo=("wardx_rot_admin",))
    yield container
    container.remove()


class LinuxLab(Lab):
    """The real Linux driver from the default registry, against a lab container."""

    def __init__(self, client, admin, box) -> None:
        super().__init__(client, admin)
        self.registry = default_registry()
        self.box = box
        self._target: dict | None = None

    async def linux_target(self) -> dict:
        if self._target is None:
            resp = await self.client.post(
                "/targets",
                headers=self.admin,
                json={
                    "name": f"lab-linux-{tag()}",
                    "address": "127.0.0.1",
                    "port": self.box.port,
                    "platform": "linux",
                    "protocol": "ssh",
                    "rotation_allowed": True,
                },
            )
            assert resp.status_code == 201, resp.text
            target = resp.json()["data"]
            # Pin the lab's host key: read it, no credential sent.
            learn = await self.client.post(
                f"/targets/{target['id']}/host-key/learn", headers=self.admin
            )
            assert learn.status_code == 200, learn.text
            self._target = learn.json()["data"]
        return self._target

    async def linux_account(self, user: str, safe_id: str | None = None) -> dict:
        return await self.account(
            password=self.box.users[user],
            target=await self.linux_target(),
            username=user,
            safe_id=safe_id,
            on_device=False,
        )


@pytest.fixture
async def linux(client, admin, box):
    settings = get_settings()
    settings.rotation_enabled = True
    yield LinuxLab(client, admin, box)
    settings.rotation_enabled = False


async def test_self_change_and_verify(linux, box):
    account = await linux.linux_account("wardx_rot_self")
    old = box.users["wardx_rot_self"]
    done = await linux.run((await linux.request(account["id"]))["id"])
    assert done["status"] == "succeeded", done
    assert done["verify_result"] == "verified"  # the wrong password was refused
    new = await linux.current(account["id"])
    assert new != old
    assert await box.login_works("wardx_rot_self", new)
    assert not await box.login_works("wardx_rot_self", old)
    for step in done["steps"]:
        for text in (step["transcript"] or "", step["detail"] or ""):
            assert new not in text and old not in text
    change = next(s for s in done["steps"] if s["step"] == "change")
    assert "passwd" in change["transcript"] and "****" in change["transcript"]


async def test_sudo_reconcile(linux, box, client, admin):
    rec = await linux.linux_account("wardx_rot_admin")
    account = await linux.linux_account("wardx_rot_rec")
    resp = await client.patch(
        f"/accounts/{account['id']}", headers=admin, json={"reconcile_account_id": rec["id"]}
    )
    assert resp.status_code == 200, resp.text
    # The device password drifted: WardX's copy no longer works.
    box.set_password("wardx_rot_rec", "Drifted-Passw0rd-Lab-1")
    done = await linux.run((await linux.request(account["id"], "reconcile"))["id"])
    assert done["status"] == "succeeded", done
    assert [s["step"] for s in done["steps"]][:2] == ["store_candidate", "reconcile"]
    new = await linux.current(account["id"])
    assert await box.login_works("wardx_rot_rec", new)
    assert (await linux.state(account["id"]))["sync_status"] == "in_sync"
    used = await linux_audit("rotation.reconcile_account_used", rec["id"])
    assert used == 1


async def linux_audit(action: str, object_id: str) -> int:
    from tests.integration.rotation.rotation_support import sql

    rows = await sql(
        "SELECT 1 FROM audit.events WHERE action = :a AND object_id = :o AND safe_id IS NOT NULL",
        a=action,
        o=object_id,
    )
    return len(rows)


async def test_verify_in_sync_then_out_of_sync(linux, box):
    account = await linux.linux_account("wardx_rot_sync")
    done = await linux.run((await linux.request(account["id"], "verify"))["id"])
    assert done["status"] == "succeeded" and done["verify_result"] == "verified"
    assert (await linux.state(account["id"]))["sync_status"] == "in_sync"
    box.set_password("wardx_rot_sync", "Changed-Behind-WardX-1")
    done = await linux.run((await linux.request(account["id"], "verify"))["id"])
    assert done["status"] == "failed"
    assert (await linux.state(account["id"]))["sync_status"] == "out_of_sync"
    assert "rotation.out_of_sync" in await linux.alerts(account["id"])


async def test_device_changed_then_crash_before_promote(linux, box):
    account = await linux.linux_account("wardx_rot_crash")
    job = await linux.request(account["id"])
    crash = CrashAt("device_answered")  # passwd succeeded; WardX dies before recording it
    await linux.run(job["id"], crash, rounds=1)
    mid = await linux.job(job["id"])
    assert mid["status"] == "candidate_stored", (
        mid["detail"],
        [(s["step"], s["outcome"], s["detail"]) for s in mid["steps"]],
    )
    assert (await linux.state(account["id"]))["secret_version"] == 1
    await linux.expire_lease(job["id"])
    done = await linux.run(job["id"])
    assert done["status"] == "succeeded", done
    assert "recover_verify_candidate" in [s["step"] for s in done["steps"]]
    assert await box.login_works("wardx_rot_crash", await linux.current(account["id"]))


async def test_safety_switches_off_means_no_connection(linux, box, client, admin):
    account = await linux.linux_account("wardx_rot_off")
    before = box.logs().count("Accepted password") + box.logs().count("Failed password")
    job = await linux.request(account["id"])
    await linux.tick(enabled=False)  # the global switch off at run time
    assert (await linux.job(job["id"]))["status"] == "failed"
    job = await linux.request(account["id"])
    await client.patch(
        f"/targets/{account['target']['id']}", headers=admin, json={"rotation_allowed": False}
    )
    try:
        await linux.tick()
        assert (await linux.job(job["id"]))["status"] == "failed"
    finally:
        await client.patch(
            f"/targets/{account['target']['id']}", headers=admin, json={"rotation_allowed": True}
        )
    after = box.logs().count("Accepted password") + box.logs().count("Failed password")
    assert after == before
    assert await box.login_works("wardx_rot_off", box.users["wardx_rot_off"])
