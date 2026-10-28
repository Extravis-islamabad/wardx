"""Throwaway Linux SSH lab containers for the rotation integration tests.

Lab only (ROTATION.md §1 rule 6): each container is created by the test from the
``wardx-lab/linux-ssh:1`` image (lab/linux), named ``wardx-lab-linux-<random>``, on the
``wardx-lab`` network, with SSH published on 127.0.0.1 only. Its accounts are
``wardx_rot_*`` users created from LAB_USERS, which is passed through the docker
process's environment (never on a command line). The container is removed by its exact
name afterwards. Nothing else on the Docker host is touched.
"""

from __future__ import annotations

import asyncio
import os
import shutil
import subprocess  # noqa: S404 - drives the local docker CLI for lab containers only
import uuid
from dataclasses import dataclass, field, replace

import asyncssh
import pytest

from src.rotation.passwords import generate
from src.rotation.policy import platform_default

IMAGE = "wardx-lab/linux-ssh:1"
NETWORK = "wardx-lab"
PREFIX = "wardx-lab-linux-"


def _docker(*args: str, env: dict | None = None, stdin: str | None = None) -> str:
    out = subprocess.run(  # noqa: S603 - fixed docker argv, no shell, no secrets
        ["docker", *args],  # noqa: S607
        capture_output=True,
        text=True,
        timeout=120,
        env=env,
        input=stdin,
        check=False,
    )
    if out.returncode != 0:
        raise RuntimeError(f"docker {args[0]} failed: {out.stderr.strip()[:300]}")
    return out.stdout


def docker_unavailable() -> str | None:
    """Why the container tests cannot run here, or None."""
    if shutil.which("docker") is None:
        return "Docker CLI not found: Linux lab container tests skipped"
    try:
        _docker("info", "--format", "{{.ServerVersion}}")
    except (RuntimeError, OSError, subprocess.TimeoutExpired):
        return "Docker daemon not reachable: Linux lab container tests skipped"
    try:
        _docker("image", "inspect", IMAGE)
    except RuntimeError:
        return f"Lab image {IMAGE} not built (sh lab/lab.sh build): container tests skipped"
    return None


requires_docker = pytest.mark.skipif(
    docker_unavailable() is not None, reason=docker_unavailable() or ""
)


@dataclass
class LinuxContainer:
    name: str
    port: int
    # user -> password the container was started with (never printed).
    users: dict[str, str] = field(repr=False)
    sudo: set[str] = field(default_factory=set)

    def logs(self) -> str:
        out = subprocess.run(  # noqa: S603
            ["docker", "logs", self.name],  # noqa: S607
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        return out.stdout + out.stderr

    def set_password(self, user: str, password: str) -> None:
        """Change a lab user's password behind WardX's back (chpasswd reads stdin)."""
        assert user.startswith("wardx_rot_")
        _docker("exec", "-i", self.name, "chpasswd", stdin=f"{user}:{password}\n")

    async def login_works(self, user: str, password: str) -> bool:
        try:
            conn = await asyncssh.connect(
                "127.0.0.1",
                self.port,
                username=user,
                password=password,
                known_hosts=None,
                client_keys=None,
                agent_path=None,
                config=None,
                preferred_auth="password",
            )
        except asyncssh.PermissionDenied:
            return False
        conn.close()
        return True

    def remove(self) -> None:
        subprocess.run(  # noqa: S603
            ["docker", "rm", "-f", self.name],  # noqa: S607
            capture_output=True,
            timeout=60,
            check=False,
        )


async def start_container(users: list[str], sudo: tuple[str, ...] = ()) -> LinuxContainer:
    """Start a container with these wardx_rot_* users (random passwords)."""
    assert all(u.startswith("wardx_rot_") for u in users)
    # The entrypoint splits LAB_USERS on ':' and expands it unquoted: no ':' or '*'.
    policy = replace(platform_default("linux"), symbols="-_.,+=@#%^")
    passwords = {u: generate(policy) for u in users}
    spec = " ".join(f"{u}:{p}{':sudo' if u in sudo else ''}" for u, p in passwords.items())
    name = PREFIX + uuid.uuid4().hex[:10]
    env = {**os.environ, "LAB_USERS": spec}
    await asyncio.to_thread(
        _docker,
        "run",
        "-d",
        "--name",
        name,
        "--network",
        NETWORK,
        "-p",
        "127.0.0.1::22",
        "-e",
        "LAB_USERS",  # value comes from the environment, not argv
        IMAGE,
        env=env,
    )
    try:
        mapped = await asyncio.to_thread(_docker, "port", name, "22/tcp")
        port = int(mapped.strip().splitlines()[0].rsplit(":", 1)[1])
        container = LinuxContainer(name, port, passwords, set(sudo))
        for _ in range(100):
            try:
                key = await asyncio.wait_for(asyncssh.get_server_host_key("127.0.0.1", port), 2)
                if key is not None and all(
                    [await container.login_works(u, p) for u, p in list(passwords.items())[:1]]
                ):
                    return container
            except (OSError, asyncssh.Error, TimeoutError):
                pass
            await asyncio.sleep(0.2)
        raise RuntimeError("lab container did not become ready")
    except BaseException:
        await asyncio.to_thread(LinuxContainer(name, 0, {}).remove)
        raise
