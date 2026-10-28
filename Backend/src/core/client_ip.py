"""The source IP of a credential-provider request.

The connection's own address, unless it is a trusted reverse proxy
(``WARDX_TRUSTED_PROXIES``, empty by default). Through trusted proxies the address is
the right-most ``X-Forwarded-For`` entry that is not itself a trusted proxy: entries to
its left are written by the client and never believed.
"""

from __future__ import annotations

import ipaddress
from collections.abc import Iterable, Sequence

from starlette.requests import Request

Network = ipaddress.IPv4Network | ipaddress.IPv6Network


def parse_networks(cidrs: Iterable[str]) -> list[Network]:
    return [ipaddress.ip_network(c.strip(), strict=False) for c in cidrs if c.strip()]


def _address(value: str) -> ipaddress.IPv4Address | ipaddress.IPv6Address | None:
    try:
        return ipaddress.ip_address(value.strip())
    except ValueError:
        return None


def in_networks(ip: str | None, networks: Sequence[Network]) -> bool:
    addr = _address(ip) if ip else None
    if addr is None:
        return False
    if isinstance(addr, ipaddress.IPv6Address) and addr.ipv4_mapped is not None:
        addr = addr.ipv4_mapped
    return any(addr.version == n.version and addr in n for n in networks)


def source_ip(request: Request, trusted_proxies: Sequence[str]) -> str | None:
    peer = request.client.host if request.client else None
    proxies = parse_networks(trusted_proxies)
    if not proxies or not in_networks(peer, proxies):
        return peer
    hops = [h.strip() for h in ",".join(request.headers.getlist("x-forwarded-for")).split(",")]
    for hop in reversed([h for h in hops if h]):
        if _address(hop) is None:
            return None  # a malformed hop: the source cannot be trusted
        if not in_networks(hop, proxies):
            return hop
    return peer
