#!/usr/bin/env python3
"""Behaves like a MonetX collector against the WardX credential provider (lab demo).

What it does, following docs/integrations/monetx-credential-provider-api.md:
1. gets an application token with client credentials (reused until shortly before expiry);
2. fetches a device credential by external_ref and caches it in memory only, keyed by
   version_id, for at most max_cache_seconds;
3. optionally logs in to the device over SSH with it (the Linux lab container), once per
   poll; if the device rejects a cached credential it re-fetches at once and retries the
   device exactly once, then stops until the next poll.

Secrets: the client secret comes from an environment variable or a file, never from the
command line. Nothing secret is printed: --reveal shows the credential masked, and only
--reveal --unmask shows it in full. Plain HTTP is refused except to a loopback address.

Example (see tools/demo/README.md):
    WARDX_CLIENT_SECRET_FILE=lab/.secrets/demo-client-secret \\
    python tools/demo/monetx_fetch_demo.py --url http://127.0.0.1:8011 \\
        --client-id wxa_... --external-ref monetx-demo-device-1 --kind ssh \\
        --login 127.0.0.1:2242 --known-hosts /path/to/known_hosts --polls 3 --interval 5
"""

from __future__ import annotations

import argparse
import asyncio
import ipaddress
import os
import random
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlparse

import httpx

TOKEN_MARGIN_SECONDS = 30
MAX_RETRIES = 4


def say(message: str) -> None:
    print(f"[collector] {message}", flush=True)


class CredentialUnavailable(Exception):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class AuthenticationFailed(Exception):
    """The device rejected the credential."""


@dataclass
class Cached:
    version_id: str
    username: str
    secret: dict = field(repr=False)
    expires_at: float
    account_id: str


@dataclass
class Provider:
    url: str
    client_id: str
    client_secret: str = field(repr=False)
    verify: str | bool = True
    token: str | None = field(default=None, repr=False)
    token_expires: float = 0.0
    cache: dict = field(default_factory=dict, repr=False)

    def __post_init__(self) -> None:
        self.http = httpx.AsyncClient(base_url=self.url, verify=self.verify, timeout=15)

    async def close(self) -> None:
        await self.http.aclose()

    async def _token(self, force: bool = False) -> str:
        if force or not self.token or time.time() > self.token_expires - TOKEN_MARGIN_SECONDS:
            resp = await self._send(
                "/api/v1/provider/token",
                {"client_id": self.client_id, "client_secret": self.client_secret},
                auth=False,
            )
            data = resp.json()["data"]
            self.token, self.token_expires = data["access_token"], time.time() + data["expires_in"]
            say(f"got an application token (valid {data['expires_in']}s)")
        return self.token

    async def _send(self, path: str, body: dict, auth: bool = True) -> httpx.Response:
        renewed = False
        resp = None
        for attempt in range(MAX_RETRIES):
            headers = {"Authorization": f"Bearer {await self._token()}"} if auth else {}
            resp = await self.http.post(path, json=body, headers=headers)
            if resp.status_code == 200:
                return resp
            error = resp.json().get("error", {})
            code = error.get("code", "")
            if code == "invalid_token" and auth and not renewed:
                say("token refused: getting a new one (once)")
                await self._token(force=True)
                renewed = True
                continue
            if resp.status_code == 429 or resp.status_code >= 500:
                wait = float(resp.headers.get("Retry-After", 2**attempt)) + random.uniform(0, 1)  # noqa: S311
                say(f"{code or resp.status_code}: backing off {wait:.1f}s")
                await asyncio.sleep(wait)
                continue
            if code.startswith("credential_unavailable") or code == "credential_not_found":
                raise CredentialUnavailable(code)
            raise SystemExit(
                f"WardX refused: HTTP {resp.status_code} {code}: {error.get('message')}"
            )
        raise SystemExit(f"WardX kept refusing (HTTP {resp.status_code if resp else '?'})")

    async def fetch(
        self, ref: str, kind: str, username: str | None, purpose: str, fresh: bool = False
    ) -> Cached:
        key = (ref, kind, username)
        hit = self.cache.get(key)
        if hit and not fresh and time.time() < hit.expires_at:
            left = int(hit.expires_at - time.time())
            say(f"cache hit: version_id={hit.version_id} (still valid {left}s)")
            return hit
        body = {"target": {"external_ref": ref}, "kind": kind, "purpose": purpose}
        if username:
            body["username"] = username
        data = (await self._send("/api/v1/provider/credentials/fetch", body)).json()["data"]
        entry = Cached(
            version_id=data["version_id"],
            username=data["username"],
            secret=data["secret"],
            expires_at=time.time() + data["max_cache_seconds"],
            account_id=data["account_id"],
        )
        say(
            f"fetched {data['kind']} credential for {data['username']}@{data['target']['name']} "
            f"version_id={data['version_id']} max_cache_seconds={data['max_cache_seconds']}"
        )
        if data["max_cache_seconds"] > 0:
            self.cache[key] = entry  # memory only
        else:
            self.cache.pop(key, None)
        return entry


def mask(value: str) -> str:
    """Nothing of the value itself: only that it is there and how long it is."""
    return f"{'*' * 8} ({len(value)} chars)"


def show_secret(entry: Cached, reveal: bool, unmask: bool) -> None:
    if not reveal:
        say(f"secret fields: {sorted(entry.secret)} (use --reveal to show them masked)")
        return
    for name, value in entry.secret.items():
        text = str(value)
        say(f"  {name} = {text if unmask else mask(text)}")


async def ssh_login(host: str, port: int, known_hosts: str, username: str, secret: dict) -> str:
    import asyncssh

    password = secret.get("password")
    if password is None:
        raise SystemExit("--login needs an SSH password credential")
    try:
        conn = await asyncio.wait_for(
            asyncssh.connect(
                host,
                port,
                username=username,
                password=password,
                known_hosts=known_hosts,
                client_keys=None,
                agent_path=None,
                config=None,
                preferred_auth="password",
            ),
            20,
        )
    except asyncssh.PermissionDenied as exc:
        raise AuthenticationFailed from exc
    async with conn:
        result = await conn.run("id -un", check=False, timeout=10)
        return str(result.stdout).strip()


async def poll(provider: Provider, args: argparse.Namespace, n: int) -> None:
    say(f"── poll {n} ──")
    try:
        cred = await provider.fetch(args.external_ref, args.kind, args.username, args.purpose)
    except CredentialUnavailable as exc:
        say(f"device status: credential unavailable ({exc.code}), not 'device down'")
        return
    show_secret(cred, args.reveal, args.unmask)
    if args.stale_cache_once and n == 1:
        # Demonstrates the client rule without a real rotation: the first login uses a
        # cached copy the device no longer accepts.
        cred = Cached(
            cred.version_id,
            cred.username,
            {"password": "stale-" + os.urandom(6).hex()},
            cred.expires_at,
            cred.account_id,
        )
        say("(demo) using a stale cached password for the first login")
    if not args.login:
        return
    host, _, port = args.login.rpartition(":")
    try:
        who = await ssh_login(host, int(port), args.known_hosts, cred.username, cred.secret)
        say(f"device login OK as {who} with version_id={cred.version_id}")
        return
    except AuthenticationFailed:
        say(f"device REJECTED cached version_id={cred.version_id}: re-fetching once")
    provider.cache.pop((args.external_ref, args.kind, args.username), None)
    try:
        fresh = await provider.fetch(
            args.external_ref, args.kind, args.username, args.purpose, fresh=True
        )
    except CredentialUnavailable as exc:
        say(f"device status: credential unavailable ({exc.code})")
        return
    try:
        who = await ssh_login(host, int(port), args.known_hosts, fresh.username, fresh.secret)
        say(f"device login OK as {who} after re-fetch, version_id={fresh.version_id}")
    except AuthenticationFailed:
        say("fresh credential rejected too: reporting authentication failure, no more retries")


def read_client_secret(args: argparse.Namespace) -> str:
    path = args.client_secret_file or os.environ.get("WARDX_CLIENT_SECRET_FILE")
    if path:
        value = Path(path).read_text().strip()
    else:
        value = os.environ.get("WARDX_CLIENT_SECRET", "").strip()
    if not value:
        raise SystemExit(
            "No client secret: set WARDX_CLIENT_SECRET, or WARDX_CLIENT_SECRET_FILE / "
            "--client-secret-file (a file path; the secret itself is never an argument)"
        )
    return value


def check_transport(url: str, ca_file: str | None) -> str | bool:
    parsed = urlparse(url)
    if parsed.scheme == "https":
        return ca_file or True
    host = parsed.hostname or ""
    try:
        loopback = host == "localhost" or ipaddress.ip_address(host).is_loopback
    except ValueError:
        loopback = False
    if parsed.scheme == "http" and loopback:
        say("WARNING: plain HTTP to a loopback WardX (local lab only; MonetX must use TLS)")
        return True
    raise SystemExit("Refusing plain HTTP to a non-loopback WardX: use https:// and --ca-file")


def parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    p.add_argument("--url", required=True, help="WardX base URL, e.g. https://wardx.example.net")
    p.add_argument("--ca-file", help="WardX CA certificate (PEM) to pin")
    p.add_argument("--client-id", required=True)
    p.add_argument("--client-secret-file", help="file holding the client secret (never the secret)")
    p.add_argument("--external-ref", required=True, help="MonetX device id (target external_ref)")
    p.add_argument("--kind", default="ssh", choices=["ssh", "snmp", "api", "enable"])
    p.add_argument("--username", help="needed when several accounts of the kind match")
    p.add_argument(
        "--purpose", default="poll", choices=["poll", "ncm_backup", "onboarding", "other"]
    )
    p.add_argument("--login", metavar="HOST:PORT", help="log in to the device over SSH")
    p.add_argument("--known-hosts", help="known_hosts file for --login (host key pinning)")
    p.add_argument("--polls", type=int, default=1)
    p.add_argument("--interval", type=float, default=5.0, help="seconds between polls")
    p.add_argument(
        "--stale-cache-once",
        action="store_true",
        help="first login uses a stale cached copy (shows the re-fetch rule)",
    )
    p.add_argument("--reveal", action="store_true", help="print the credential, masked")
    p.add_argument("--unmask", action="store_true", help="with --reveal: print it in full")
    args = p.parse_args(argv)
    if args.login and not args.known_hosts:
        p.error("--login needs --known-hosts (the device's host key is always verified)")
    if args.unmask and not args.reveal:
        p.error("--unmask only works with --reveal")
    return args


async def main(argv: list[str]) -> None:
    args = parse_args(argv)
    verify = check_transport(args.url, args.ca_file)
    provider = Provider(args.url, args.client_id, read_client_secret(args), verify)
    try:
        for n in range(1, args.polls + 1):
            await poll(provider, args, n)
            if n < args.polls:
                await asyncio.sleep(args.interval)
    finally:
        await provider.close()


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1:]))
