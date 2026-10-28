"""SSH connections to targets with a vaulted credential, shared by the gateway and rotation.

Host keys are trusted on first use: the first key a target presents is pinned
on the target row, and every later connection must present that exact key, or
the credential is never sent. An administrator resets the pin after a
legitimate key change.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

import asyncssh


class TargetError(Exception):
    """Connecting to or logging in on the target failed; the message is user-facing."""


class HostKeyMismatch(TargetError):
    pass


class CredentialRejected(TargetError):
    pass


@dataclass(frozen=True)
class SshTarget:
    name: str
    address: str
    port: int
    pinned_key: str | None


@dataclass(frozen=True)
class HostKeyTrust:
    # Pin a first-seen key; False if another key won the race.
    learn: Callable[[str, str], Awaitable[bool]]
    # Record a mismatch (presented fingerprint, if it could be read).
    mismatch: Callable[[str | None], Awaitable[None]]


def host_key_algs(key: asyncssh.SSHKey) -> list[str]:
    """Signature algorithms to offer for a pinned key.

    Not ``key.get_algorithm()``: for RSA that is ``ssh-rsa`` (SHA-1), which
    current OpenSSH refuses; the key's SHA-2 variants come first in this list.
    """
    return [alg.decode() for alg in key.sig_algorithms]


def openssh_public(key: asyncssh.SSHKey) -> str:
    return key.export_public_key("openssh").decode().strip()


async def open_ssh(
    target: SshTarget,
    trust: HostKeyTrust,
    *,
    username: str,
    secret_type: str,
    secret: str,
    timeout: float,  # noqa: ASYNC109 - applied per step below
) -> asyncssh.SSHClientConnection:
    host, port = target.address, target.port
    if secret_type.startswith("snmp"):
        # Never send an SNMP document to a device as an SSH password.
        raise TargetError("SNMP credentials cannot open an SSH session")
    try:
        if target.pinned_key is None:
            key = await asyncio.wait_for(asyncssh.get_server_host_key(host, port), timeout)
            if key is None:
                raise TargetError("Target did not present a host key")
            if not await trust.learn(openssh_public(key), key.get_fingerprint("sha256")):
                raise TargetError("Host key was pinned by a concurrent connection; retry")
            trusted = key
        else:
            trusted = asyncssh.import_public_key(target.pinned_key)

        credentials: dict[str, object]
        if secret_type == "ssh_key":
            credentials = {"client_keys": [asyncssh.import_private_key(secret)]}
        else:
            credentials = {
                "password": secret,
                "client_keys": None,
                "preferred_auth": "keyboard-interactive,password",
            }
        return await asyncio.wait_for(
            asyncssh.connect(
                host,
                port,
                username=username,
                known_hosts=([trusted], [], []),
                server_host_key_algs=host_key_algs(trusted) if target.pinned_key else (),
                agent_path=None,
                config=None,
                **credentials,
            ),
            timeout,
        )
    except asyncssh.HostKeyNotVerifiable as exc:
        presented = None
        try:
            key = await asyncio.wait_for(asyncssh.get_server_host_key(host, port), timeout)
            presented = key.get_fingerprint("sha256") if key else None
        except (OSError, asyncssh.Error, TimeoutError):
            pass
        await trust.mismatch(presented)
        raise HostKeyMismatch(
            f"HOST KEY MISMATCH for {target.name}: it presented "
            f"{presented or 'an unknown key'}, not the pinned key. The credential was not "
            "sent. Ask an administrator to check the device and reset its host key in WardX."
        ) from exc
    except asyncssh.PermissionDenied as exc:
        raise CredentialRejected(
            f"{target.name} rejected the vaulted credential for {username}. "
            "The stored secret may be out of date."
        ) from exc
    except TimeoutError as exc:
        raise TargetError(f"Timed out connecting to {target.name} ({host}:{port})") from exc
    except (OSError, asyncssh.Error) as exc:
        raise TargetError(f"Could not connect to {target.name}: {exc}") from exc
