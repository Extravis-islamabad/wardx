"""The MikroTik CHR lab (``wardx-lab-mikrotik``, lab/README.md) for rotation tests.

Lab only (ROTATION.md §1 rule 6). These helpers:
- create, change and remove only ``wardx_rot_*`` users, and never touch ``admin``
  (it is only used to log in and manage the test users);
- may toggle the api-ssl service and its certificate, always restoring both
  (``api_ssl_disabled`` and ``certificate_swapped`` restore in ``finally``, and
  ``check_restored`` verifies the original state);
- never restart, recreate or remove the container, and never write certificate or key
  material on this machine (a temporary certificate is generated ON the device and
  removed there).

The admin password is read from lab/.secrets/mikrotik-admin and never printed. The
helpers' own trust anchors (the API-SSL certificate and SSH host key) are read once per
run before any credential is sent; the product never does this (it pins only after an
administrator compares and accepts).
"""

from __future__ import annotations

import asyncio
import contextlib
import secrets
import shutil
import subprocess  # noqa: S404 - only `docker ps` for the lab container's state
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from pathlib import Path

import asyncssh
import pytest

from src.rotation.passwords import generate
from src.rotation.policy import platform_default
from src.transport import routeros_api as api
from tests.lab_gate import lab_skip_reason

CONTAINER = "wardx-lab-mikrotik"
HOST = "127.0.0.1"
SSH_PORT, API_PORT, API_SSL_PORT = 2232, 8738, 8739
LAB_CERT = "wardx-lab-api"
ADMIN_FILE = Path(__file__).resolve().parents[4] / "lab" / ".secrets" / "mikrotik-admin"
PREFIX = "wardx_rot_"
# Bound once, so tests that count the driver's logins never count the helper's own.
_login = api.login


def _container_running() -> bool:
    if shutil.which("docker") is None:
        return False
    out = subprocess.run(  # noqa: S603 - fixed argv, our own lab container only
        ["docker", "ps", "--filter", f"name=^/{CONTAINER}$", "--format", "{{.Names}}"],  # noqa: S607
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )
    return out.returncode == 0 and out.stdout.strip() == CONTAINER


def chr_unavailable() -> str | None:
    """Why the CHR tests cannot run here, or None."""
    if not _container_running():
        return f"Docker or the {CONTAINER} container is not running: CHR tests skipped"
    if not ADMIN_FILE.is_file():
        return "lab/.secrets/mikrotik-admin is missing: CHR tests skipped"
    try:
        asyncio.run(api.fetch_certificate(HOST, API_SSL_PORT, 5))
    except api.Unavailable:
        return f"API-SSL on {HOST}:{API_SSL_PORT} does not answer: CHR tests skipped"
    return None


# The opt-in gate first: without WARDX_LAB=mikrotik nothing below probes the CHR.
_REASON = lab_skip_reason("mikrotik") or chr_unavailable()
requires_chr = pytest.mark.skipif(_REASON is not None, reason=_REASON or "")


def new_password() -> str:
    return generate(platform_default("mikrotik_routeros"))


@dataclass
class Chr:
    """Admin access to the lab CHR, for test set-up only."""

    cert_pem: str = field(repr=False)
    cert_fingerprint: str
    host_key: asyncssh.SSHKey = field(repr=False)
    created: set[str] = field(default_factory=set)
    _admin: str = field(default="", repr=False)
    _ssh: asyncssh.SSHClientConnection | None = field(default=None, repr=False)

    @classmethod
    async def connect(cls) -> Chr:
        pem, fingerprint = await api.fetch_certificate(HOST, API_SSL_PORT, 10)
        key = await asyncssh.get_server_host_key(HOST, SSH_PORT)
        return cls(pem, fingerprint, key, _admin=ADMIN_FILE.read_text().strip())

    @contextlib.asynccontextmanager
    async def api(self) -> AsyncIterator[api.ApiConnection]:
        """A fresh admin API-SSL session (pinned to the certificate read at start)."""
        conn = await api.open_api_ssl(
            HOST,
            API_SSL_PORT,
            pinned_pem=self.cert_pem,
            pinned_fingerprint=self.cert_fingerprint,
            timeout=20,
        )
        try:
            assert await _login(conn, "admin", self._admin)
            yield conn
        finally:
            await conn.close()

    async def cli(self, command: str) -> str:
        """One RouterOS command over SSH as admin, on one connection kept for the run
        (RouterOS throttles rapid SSH logins). Never used with a secret in it."""
        assert "password" not in command.lower()
        if self._ssh is None:
            self._ssh = await asyncssh.connect(
                HOST,
                SSH_PORT,
                username="admin",
                password=self._admin,
                known_hosts=([self.host_key], [], []),
                client_keys=None,
                agent_path=None,
                config=None,
                preferred_auth="password",
            )
        result = await asyncio.wait_for(self._ssh.run(command, check=False), 60)
        out = str(result.stdout)
        assert result.exit_status == 0 and "failure:" not in out, f"{command}: {out[-300:]}"
        return out

    async def close(self) -> None:
        if self._ssh is not None:
            self._ssh.close()
            self._ssh = None

    # ── wardx_rot_* users ──

    async def add_user(self, purpose: str, group: str = "read", password: str | None = None):
        """A new wardx_rot_* user with a generated (or the given, possibly empty)
        password. Returns (name, password)."""
        name = f"{PREFIX}{purpose}_{secrets.token_hex(3)}"
        password = new_password() if password is None else password
        async with self.api() as conn:
            await conn.call(
                "/user/add",
                {"name": name, "group": group, "password": password},
                secret_attrs=("password",),
            )
        self.created.add(name)
        return name, password

    async def set_password(self, name: str, password: str) -> None:
        """Change a test user's password behind WardX's back."""
        assert name.startswith(PREFIX) and name in self.created
        async with self.api() as conn:
            rows = await conn.call("/user/print", queries=[f"?name={name}"])
            await conn.call(
                "/user/set",
                {".id": rows[0][".id"], "password": password},
                secret_attrs=("password",),
            )

    async def remove_user(self, name: str) -> None:
        assert name.startswith(PREFIX) and name != "admin"
        async with self.api() as conn:
            for row in await conn.call("/user/print", queries=[f"?name={name}"]):
                if row.get("name") == name:
                    await conn.call("/user/remove", {".id": row[".id"]})
        self.created.discard(name)

    async def remove_all(self) -> None:
        for name in sorted(self.created):
            await self.remove_user(name)

    async def users(self) -> list[str]:
        async with self.api() as conn:
            return sorted(r["name"] for r in await conn.call("/user/print"))

    async def login_works(self, name: str, password: str) -> bool:
        conn = await api.open_api_ssl(
            HOST,
            API_SSL_PORT,
            pinned_pem=self.cert_pem,
            pinned_fingerprint=self.cert_fingerprint,
            timeout=20,
        )
        try:
            return await _login(conn, name, password)
        finally:
            await conn.close()

    async def history_and_log(self) -> str:
        """The device's /system history and /log text, to check no password leaked."""
        async with self.api() as conn:
            rows = await conn.call("/system/history/print", {"detail": ""})
            rows += await conn.call("/log/print")
        return "\n".join(str(sorted(r.items())) for r in rows)

    async def device_fingerprint(self) -> str:
        """The lab certificate's fingerprint as RouterOS itself reports it."""
        async with self.api() as conn:
            rows = await conn.call("/certificate/print", queries=[f"?name={LAB_CERT}"])
        return rows[0]["fingerprint"]

    # ── service toggles, always restored ──

    async def api_ssl_state(self) -> tuple[str, str]:
        out = await self.cli(
            ':put ([/ip service get api-ssl disabled] . "," . '
            "[/ip service get api-ssl certificate])"
        )
        disabled, _, cert = out.strip().partition(",")
        return disabled, cert

    async def restore(self) -> None:
        await self.cli(f"/ip service set api-ssl certificate={LAB_CERT} disabled=no")

    async def check_restored(self) -> None:
        assert await self.api_ssl_state() == ("false", LAB_CERT)
        fingerprint = None
        for _ in range(20):
            try:
                _, fingerprint = await api.fetch_certificate(HOST, API_SSL_PORT, 5)
                break
            except api.Unavailable:
                await asyncio.sleep(0.5)
        assert fingerprint == self.cert_fingerprint

    @contextlib.asynccontextmanager
    async def api_ssl_disabled(self) -> AsyncIterator[None]:
        await self.cli("/ip service set api-ssl disabled=yes")
        try:
            yield
        finally:
            await self.restore()
            await self.check_restored()

    @contextlib.asynccontextmanager
    async def certificate_swapped(self) -> AsyncIterator[str]:
        """api-ssl presents a temporary certificate generated ON the device (never on
        this machine); restores the lab certificate and removes the temporary one.
        Yields the temporary certificate's fingerprint as the device presents it."""
        name = f"{PREFIX}cert_{secrets.token_hex(3)}"
        presented = None
        try:
            async with self.api() as conn:
                # RouterOS 7.25 self-signs only with key-cert-sign in key-usage.
                await conn.call(
                    "/certificate/add",
                    {
                        "name": name,
                        "common-name": name,
                        "key-size": "prime256v1",
                        "days-valid": "2",
                        "key-usage": "digital-signature,key-encipherment,key-cert-sign,tls-server",
                    },
                )
                rows = await conn.call("/certificate/print", queries=[f"?name={name}"])
                await conn.call("/certificate/sign", {".id": rows[0][".id"]})
            await self.cli(f"/ip service set api-ssl certificate={name}")
            for _ in range(20):
                try:
                    _, presented = await api.fetch_certificate(HOST, API_SSL_PORT, 5)
                    if presented != self.cert_fingerprint:
                        break
                except api.Unavailable:
                    pass
                await asyncio.sleep(0.5)
            assert presented and presented != self.cert_fingerprint, "certificate not swapped"
            yield presented
        finally:
            await self.restore()
            await self.check_restored()
            async with self.api() as conn:
                for row in await conn.call("/certificate/print", queries=[f"?name={name}"]):
                    await conn.call("/certificate/remove", {".id": row[".id"]})
