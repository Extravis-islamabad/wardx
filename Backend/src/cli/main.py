"""``wardx``: operator commands, run on a WardX host with that node's configuration.

    wardx recordings encrypt [--limit N]            migrate plaintext recordings (HA_DR.md §5.1)
    wardx recordings encrypt --remove-verified-originals [--limit N]

Run as ``.venv/bin/python -m src.cli ...`` from Backend/ (the ``wardx`` wrapper does that).
Each command starts like a node does (keys, migrations, canary check) and audits its work.
"""

from __future__ import annotations

import argparse
import asyncio
from collections.abc import Callable

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


COMMANDS = {
    ("recordings", "encrypt"): _recordings_encrypt,
}


async def run(argv: list[str], *, init: bool = True, out: Callable[[str], None] = print) -> int:
    """``init``: start like a node (keys, migrations, canary). Tests pass False."""
    args = _parser().parse_args(argv)
    if init:
        from src.core.app_factory import startup

        await startup(get_settings())
    try:
        return await COMMANDS[(args.area, args.command)](args, out)
    finally:
        if init:
            from src.core.db import dispose_engine

            await dispose_engine()


def main(argv: list[str]) -> int:
    return asyncio.run(run(argv))
