"""Gateway side of connecting to a target: host-key pins go through the broker."""

from __future__ import annotations

import asyncssh

from src.gateway.broker import Broker, Grant
from src.transport.ssh import (
    HostKeyMismatch,
    HostKeyTrust,
    SshTarget,
    TargetError,
    host_key_algs,
    open_ssh,
)

__all__ = ["HostKeyMismatch", "TargetError", "connect", "host_key_algs"]


async def connect(
    grant: Grant,
    broker: Broker,
    timeout: float,  # noqa: ASYNC109 - passed through to open_ssh
) -> asyncssh.SSHClientConnection:
    return await open_ssh(
        SshTarget(
            grant.target.name, grant.target.address, grant.target.port, grant.target.ssh_host_key
        ),
        HostKeyTrust(
            learn=lambda key, fp: broker.pin_host_key(grant, key, fp),
            mismatch=lambda presented: broker.host_key_mismatch(grant, presented),
        ),
        username=grant.account_username,
        secret_type=grant.secret_type,
        secret=grant.secret,
        timeout=timeout,
    )
