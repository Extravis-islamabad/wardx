"""Connecting to the target with the vaulted credential.

Host keys are trusted on first use: the first key a target presents is pinned
on the target row, and every later connection must present that exact key, or
the credential is never sent. An administrator resets the pin after a
legitimate key change.
"""

from __future__ import annotations

import asyncio

import asyncssh

from src.gateway.broker import Broker, Grant


class TargetError(Exception):
    """Connecting to or logging in on the target failed; the message is shown to the user."""


class HostKeyMismatch(TargetError):
    pass


def host_key_algs(key: asyncssh.SSHKey) -> list[str]:
    """Signature algorithms to offer for a pinned key.

    Not ``key.get_algorithm()``: for RSA that is ``ssh-rsa`` (SHA-1), which
    current OpenSSH refuses; the key's SHA-2 variants come first in this list.
    """
    return [alg.decode() for alg in key.sig_algorithms]


def _openssh(key: asyncssh.SSHKey) -> str:
    return key.export_public_key("openssh").decode().strip()


async def connect(
    grant: Grant,
    broker: Broker,
    timeout: float,  # noqa: ASYNC109 - per-step timeouts below
) -> asyncssh.SSHClientConnection:
    host, port = grant.target.address, grant.target.port
    pinned = grant.target.ssh_host_key
    try:
        if pinned is None:
            key = await asyncio.wait_for(asyncssh.get_server_host_key(host, port), timeout)
            if key is None:
                raise TargetError("Target did not present a host key")
            fingerprint = key.get_fingerprint("sha256")
            if not await broker.pin_host_key(grant, _openssh(key), fingerprint):
                raise TargetError("Host key was pinned by a concurrent session; reconnect")
            trusted = key
        else:
            trusted = asyncssh.import_public_key(pinned)

        credentials: dict[str, object]
        if grant.secret_type == "ssh_key":
            credentials = {"client_keys": [asyncssh.import_private_key(grant.secret)]}
        else:
            credentials = {
                "password": grant.secret,
                "client_keys": None,
                "preferred_auth": "keyboard-interactive,password",
            }
        return await asyncio.wait_for(
            asyncssh.connect(
                host,
                port,
                username=grant.account_username,
                known_hosts=([trusted], [], []),
                server_host_key_algs=host_key_algs(trusted) if pinned else (),
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
        await broker.host_key_mismatch(grant, presented)
        raise HostKeyMismatch(
            f"HOST KEY MISMATCH for {grant.target.name}: it presented "
            f"{presented or 'an unknown key'}, not the pinned key. The credential was not "
            "sent. Ask an administrator to check the device and reset its host key in WardX."
        ) from exc
    except asyncssh.PermissionDenied as exc:
        raise TargetError(
            f"{grant.target.name} rejected the vaulted credential for {grant.account_username}. "
            "The stored secret may be out of date."
        ) from exc
    except TimeoutError as exc:
        raise TargetError(f"Timed out connecting to {grant.target.name} ({host}:{port})") from exc
    except (OSError, asyncssh.Error) as exc:
        raise TargetError(f"Could not connect to {grant.target.name}: {exc}") from exc
