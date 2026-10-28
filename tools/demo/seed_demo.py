#!/usr/bin/env python3
"""Prepares a scratch WardX for the MonetX fetch demo, through WardX's own admin API.

    seed    a Linux lab target (external_ref = a MonetX-style device id, host key pinned
            after a probe, rotation allowed), its account in the Default safe, an
            application identity allowed from 127.0.0.1 with 'fetch' on that safe.
            The client secret goes to --secret-out (mode 0600) and is never printed.
    rotate  asks WardX to rotate the account now (the scheduler's worker runs it) and
            waits for the job to finish.

Lab and scratch databases only. Secrets come from files: the WardX admin password
(WARDX_ADMIN_PASSWORD_FILE) and the lab account's password (--device-password-file).
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

import httpx


def say(message: str) -> None:
    print(f"[seed] {message}", flush=True)


def ok(resp: httpx.Response, *expected: int) -> dict:
    if resp.status_code not in (expected or (200, 201)):
        error = resp.json().get("error", {})
        raise SystemExit(
            f"{resp.request.method} {resp.request.url.path}: {resp.status_code} "
            f"{error.get('code')}: {error.get('message')}"
        )
    return resp.json()["data"]


def admin_client(url: str) -> httpx.Client:
    path = os.environ.get("WARDX_ADMIN_PASSWORD_FILE")
    if not path:
        raise SystemExit("Set WARDX_ADMIN_PASSWORD_FILE to a file holding the admin password")
    c = httpx.Client(base_url=f"{url}/api/v1", timeout=30)
    login = ok(
        c.post(
            "/auth/login", json={"username": "admin", "password": Path(path).read_text().strip()}
        )
    )
    c.headers["Authorization"] = f"Bearer {login['access_token']}"
    return c


def write_secret(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as fh:
        fh.write(value + "\n")


def seed(args: argparse.Namespace) -> None:
    c = admin_client(args.url)
    default_safe = "00000000-0000-0000-0000-000000005afe"
    target = ok(
        c.post(
            "/targets",
            json={
                "name": "monetx-demo-device",
                "address": "127.0.0.1",
                "port": args.device_port,
                "platform": "linux",
                "protocol": "ssh",
                "external_ref": args.external_ref,
                "rotation_allowed": True,
            },
        )
    )
    probe = ok(c.post(f"/targets/{target['id']}/host-key/probe"))
    # In production an administrator compares this with the device before accepting.
    ok(
        c.post(
            f"/targets/{target['id']}/host-key/accept",
            json={"fingerprint": probe["presented_fingerprint"]},
        )
    )
    say(
        f"target {target['name']} external_ref={args.external_ref}, host key "
        f"{probe['presented_fingerprint']} pinned"
    )
    account = ok(
        c.post(
            "/accounts",
            json={
                "target_id": target["id"],
                "safe_id": default_safe,
                "username": args.device_user,
                "secret": Path(args.device_password_file).read_text().strip(),
            },
        )
    )
    say(f"account {args.device_user} id={account['id']} in the Default safe")
    created = ok(
        c.post(
            "/apps",
            json={
                "name": "monetx-demo-collector",
                "ip_allowlist": ["127.0.0.1/32"],
                "rate_limit_per_minute": 60,
                "description": "MonetX fetch demo (lab)",
            },
        )
    )
    write_secret(Path(args.secret_out), created["client_secret"])
    ok(
        c.post(
            f"/safes/{default_safe}/members",
            json={
                "principal_type": "app",
                "principal_key": created["app"]["id"],
                "permissions": ["fetch"],
            },
        )
    )
    ok(
        c.put(
            f"/safes/{default_safe}/app-fetch",
            json={"allow_app_fetch": False, "app_cache_seconds": args.cache_seconds},
        )
    )
    say(f"application monetx-demo-collector client_id={created['client_id']}")
    say(f"client secret written to {args.secret_out} (0600; not printed)")
    say(f"app_cache_seconds={args.cache_seconds} on the Default safe")


def rotate(args: argparse.Namespace) -> None:
    c = admin_client(args.url)
    accounts = ok(c.get("/accounts", params={"search": args.device_user}))
    account = next(a for a in accounts if a["target"]["name"] == "monetx-demo-device")
    job = ok(c.post(f"/accounts/{account['id']}/rotate", json={"reason": "MonetX fetch demo"}), 202)
    say(f"rotation job {job['id']} queued")
    for _ in range(90):
        status = ok(c.get(f"/rotation/jobs/{job['id']}"))["status"]
        if status in ("succeeded", "failed", "needs_attention", "changed_unverified", "cancelled"):
            say(f"rotation job finished: {status}")
            return
        time.sleep(2)
    raise SystemExit("rotation job did not finish in 3 minutes")


def main(argv: list[str]) -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    p.add_argument("command", choices=["seed", "rotate"])
    p.add_argument("--url", default="http://127.0.0.1:8011")
    p.add_argument("--device-port", type=int, default=2242)
    p.add_argument("--device-user", default="wardx_rot_demo")
    p.add_argument("--device-password-file", default="lab/.secrets/linux-demo")
    p.add_argument("--external-ref", default="monetx-demo-device-1")
    p.add_argument("--secret-out", default="lab/.secrets/demo-client-secret")
    p.add_argument("--cache-seconds", type=int, default=300)
    args = p.parse_args(argv)
    seed(args) if args.command == "seed" else rotate(args)


if __name__ == "__main__":
    main(sys.argv[1:])
