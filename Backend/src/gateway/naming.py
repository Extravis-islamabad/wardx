"""The SSH login name carries who is connecting and where to.

    ssh -p 2222 alice%root%core-sw-1@wardx      user alice, account root on target core-sw-1
    ssh -p 2222 alice%core-sw-1@wardx           the target's only account

``%`` is used because ``@`` needs quoting in most SSH clients and ``:`` is
common in Windows account names.
"""

from __future__ import annotations

from dataclasses import dataclass

SEPARATOR = "%"


@dataclass(frozen=True)
class GatewayLogin:
    wardx_user: str
    account: str | None
    target: str


def parse_login(name: str) -> GatewayLogin:
    parts = name.split(SEPARATOR)
    if any(not p.strip() for p in parts):
        raise ValueError("empty part in login name")
    if len(parts) == 3:
        return GatewayLogin(parts[0], parts[1], parts[2])
    if len(parts) == 2:
        return GatewayLogin(parts[0], None, parts[1])
    raise ValueError(f"expected user{SEPARATOR}account{SEPARATOR}target")


def login_hint(user: str, account: str, target: str, host: str, port: int) -> str:
    return f"ssh -p {port} {user}{SEPARATOR}{account}{SEPARATOR}{target}@{host}"
