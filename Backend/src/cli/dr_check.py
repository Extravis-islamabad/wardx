"""`wardx dr post-failover-check` (HA_DR.md §6.1): list, verify, reconcile, report, audit."""

from __future__ import annotations

import argparse
import asyncio
from collections.abc import Callable
from pathlib import Path

from src.core.config import get_settings
from src.core.db import session_factory
from src.dependencies.rotation import build_dr_failover_service
from src.models import utcnow
from src.services.rotation.dr_failover_service import scan_export


async def run_post_failover_check(args: argparse.Namespace, out: Callable[[str], None]) -> int:
    until = args.until or utcnow()
    export = None
    if args.audit_export:
        text = await asyncio.to_thread(Path(args.audit_export).read_text)
        export = scan_export(text.splitlines(), args.since, until)
    async with session_factory()() as session:
        service = build_dr_failover_service(session)
        listed = await service.accounts_in_window(args.since, until, export)
        out(f"Loss window {args.since.isoformat()} .. {until.isoformat()}")
        if export:
            out(f"Audit export: {export.lines} events read, {export.skipped} unreadable skipped")
        out(f"{len(listed)} account(s) rotated in the window:")
        for a in listed:
            src = "+".join(n for n, f in (("db", a.from_db), ("export", a.from_export)) if f)
            out(f"  {a.account_id}  {a.label}  [{src}]{'' if a.known else '  UNKNOWN HERE'}")
        details = {
            "since": args.since.isoformat(),
            "until": until.isoformat(),
            "dry_run": args.dry_run,
            "audit_export": bool(export),
            "accounts": [str(a.account_id) for a in listed],
        }
        if args.dry_run:
            out("Dry run: nothing queued.")
            await service.audit_run(details, ok=True)
            return 0
        if not get_settings().rotation_enabled:
            out("WARNING: WARDX_ROTATION_ENABLED is off; verify jobs will be refused until on.")

        jobs: dict = {}
        for a in listed:
            job_id, note = await service.queue_verify(a)
            out(f"  {a.label}: {note}")
            if job_id is not None:
                jobs[a.account_id] = job_id

        deadline = asyncio.get_running_loop().time() + args.wait_seconds
        states: dict = {}
        while True:
            states = await service.job_states(list(jobs.values()))
            if all(service.finished(s) for s in states.values()):
                break
            if asyncio.get_running_loop().time() >= deadline:
                break
            await asyncio.sleep(2)

        report: dict[str, str] = {}
        failed = 0
        for a in listed:
            job_id = jobs.get(a.account_id)
            status = states.get(job_id) if job_id else None
            if status is None:
                report[str(a.account_id)] = "manual: no verify ran"
                failed += 1
            elif not service.finished(status):
                report[str(a.account_id)] = f"still {status}: run the check again later"
                failed += 1
            elif service.verified(status):
                report[str(a.account_id)] = "verified"
            else:
                report[str(a.account_id)] = await service.reconcile(a.account_id)
                failed += 1
        out("Report:")
        for a in listed:
            out(f"  {a.label}: {report[str(a.account_id)]}")
        await service.audit_run({**details, "results": report}, ok=failed == 0)
    return 0 if failed == 0 else 1
