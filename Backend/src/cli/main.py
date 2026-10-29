"""``wardx``: operator commands, run on a WardX host with that node's configuration.

    wardx recordings encrypt [--limit N]            migrate plaintext recordings (HA_DR.md §5.1)
    wardx recordings encrypt --remove-verified-originals [--limit N]
    wardx dr post-failover-check --since TIME [--audit-export FILE] [--dry-run]   (§6.1)
    wardx backup encrypt --name NAME [--in F] [--out G] | backup decrypt [--in G] [--out F]
    wardx restore verify [--restore-point T] [--sample N] [--json F]   (on a restored DB, §7)
    wardx restore record-drill --result F                              (on production)

Run as ``.venv/bin/python -m src.cli ...`` from Backend/ (the ``wardx`` wrapper does that).
Each command starts like a node does (keys, migrations, canary check) and audits its work.
"""

from __future__ import annotations

import argparse
import asyncio
from collections.abc import Callable
from datetime import datetime

from src.core.config import get_settings


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="wardx", description=__doc__.split("\n")[0])
    sub = p.add_subparsers(dest="area", required=True)

    rec = sub.add_parser("recordings", help="session recordings").add_subparsers(
        dest="command", required=True
    )
    enc = rec.add_parser("encrypt", help="encrypt legacy plaintext recordings (resumable)")
    enc.add_argument(
        "--remove-verified-originals",
        action="store_true",
        help="separate run: delete originals whose encrypted copy verifies again now",
    )
    enc.add_argument("--limit", type=int, default=None, help="stop after N recordings")

    bak = sub.add_parser("backup", help="encrypted backup archives").add_subparsers(
        dest="command", required=True
    )
    for name, text in (("encrypt", "encrypt a file or stdin"), ("decrypt", "decrypt an archive")):
        cmd = bak.add_parser(name, help=text)
        cmd.add_argument("--in", dest="src", default="-", help="input file, or - for stdin")
        cmd.add_argument("--out", dest="dst", default="-", help="output file, or - for stdout")
        if name == "encrypt":
            cmd.add_argument("--name", required=True, help="archive name, bound into the AAD")

    res = sub.add_parser("restore", help="restore verification").add_subparsers(
        dest="command", required=True
    )
    ver = res.add_parser("verify", help="verify a RESTORED database (WARDX_DATABASE_URL)")
    ver.add_argument("--restore-point", type=datetime.fromisoformat, default=None)
    ver.add_argument("--sample", type=int, default=20, help="secrets to sample-decrypt")
    ver.add_argument("--json", dest="json_out", default=None, help="write the result here")
    rec = res.add_parser("record-drill", help="record a drill result on this database")
    rec.add_argument("--result", required=True, help="the JSON written by restore verify")

    dr = sub.add_parser("dr", help="disaster recovery").add_subparsers(
        dest="command", required=True
    )
    check = dr.add_parser(
        "post-failover-check", help="verify and reconcile accounts rotated in the loss window"
    )
    check.add_argument(
        "--since",
        required=True,
        type=datetime.fromisoformat,
        help="time of the last confirmed replication (ISO 8601; UTC without an offset)",
    )
    check.add_argument(
        "--until", type=datetime.fromisoformat, default=None, help="failover time (default now)"
    )
    check.add_argument("--audit-export", default=None, help="forwarded audit export, JSON lines")
    check.add_argument("--dry-run", action="store_true", help="list only; queue nothing")
    check.add_argument(
        "--wait-seconds", type=int, default=900, help="how long to wait for the verify jobs"
    )
    return p


async def _recordings_encrypt(args: argparse.Namespace, out: Callable[[str], None]) -> int:
    from src.core.db import session_factory
    from src.dependencies.sessions import build_recording_migration_service

    async with session_factory()() as session:
        service = build_recording_migration_service(session)
        if args.remove_verified_originals:
            report = await service.remove_verified_originals(limit=args.limit)
        else:
            report = await service.encrypt_all(limit=args.limit)
    for line in report.lines():
        out(line)
    return 1 if report.failed else 0


async def _dr_post_failover_check(args: argparse.Namespace, out: Callable[[str], None]) -> int:
    from src.cli.dr_check import run_post_failover_check

    return await run_post_failover_check(args, out)


async def _backup(args: argparse.Namespace, out: Callable[[str], None]) -> int:
    import sys

    from src.keys.runtime import key_provider
    from src.services.backup.archive_crypto import decrypt_stream, encrypt_stream

    # A one-shot CLI process: blocking file I/O is fine here.
    src = sys.stdin.buffer if args.src == "-" else open(args.src, "rb")  # noqa: ASYNC230, SIM115
    dst = sys.stdout.buffer if args.dst == "-" else open(args.dst, "xb")  # noqa: ASYNC230, SIM115
    try:
        if args.command == "encrypt":
            await encrypt_stream(key_provider(), args.name, src, dst)
        else:
            await decrypt_stream(key_provider(), src, dst)
    finally:
        for fh in (src, dst):
            if fh not in (sys.stdin.buffer, sys.stdout.buffer):
                fh.close()
    return 0


async def _restore(args: argparse.Namespace, out: Callable[[str], None]) -> int:
    import json
    from pathlib import Path

    from src.core.db import session_factory
    from src.dependencies.health import build_restore_service

    async with session_factory()() as session:
        service = build_restore_service(session)
        if args.command == "verify":
            result = await service.verify(sample=args.sample, restore_point=args.restore_point)
            text = json.dumps(result, indent=2, default=str)
            if args.json_out:
                await asyncio.to_thread(Path(args.json_out).write_text, text)
            out(text)
            return 0 if result["ok"] else 1
        result = json.loads(await asyncio.to_thread(Path(args.result).read_text))
        drill_id = await service.record_drill(result)
        out(f"restore drill {drill_id} recorded: {'ok' if result.get('ok') else 'FAILED'}")
        return 0


COMMANDS = {
    ("recordings", "encrypt"): _recordings_encrypt,
    ("dr", "post-failover-check"): _dr_post_failover_check,
    ("backup", "encrypt"): _backup,
    ("backup", "decrypt"): _backup,
    ("restore", "verify"): _restore,
    ("restore", "record-drill"): _restore,
}


async def run(argv: list[str], *, init: bool = True, out: Callable[[str], None] = print) -> int:
    """``init``: start like a node (keys, migrations, canary). Tests pass False."""
    args = _parser().parse_args(argv)
    keys_only = args.area == "backup"  # archives need the KEK, never the database
    if init and keys_only:
        from src.core.app_factory import load_key_provider

        load_key_provider(get_settings())
    elif init:
        from src.core.app_factory import startup

        await startup(get_settings())
    try:
        return await COMMANDS[(args.area, args.command)](args, out)
    finally:
        if init and not keys_only:
            from src.core.db import dispose_engine

            await dispose_engine()


def main(argv: list[str]) -> int:
    return asyncio.run(run(argv))
