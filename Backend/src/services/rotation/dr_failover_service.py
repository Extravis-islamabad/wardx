"""`wardx dr post-failover-check`: the DR activation step of HA_DR.md §6.1.

1. List every account rotated in the possible loss window (``since`` = last confirmed
   replication, ``until`` = failover), from the promoted database's audit trail and rotation
   jobs and, if given, a forwarded audit or SIEM export (JSON lines of WardX audit events),
   which catches rotations the DR copy never received.
2. Queue a normal verify job on each (negative check included).
3. Reconcile each account whose verify fails, through its reconcile account; accounts
   without one are flagged out of sync and listed for manual action.
4. The whole run is audited. A dry run lists only.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from src.contracts.dto.rotation.rotation_dto import (
    OPEN_STATES,
    OUT_OF_SYNC,
    PENDING,
    RECONCILE,
    SUCCEEDED,
    VERIFY,
)
from src.core.context import SYSTEM_ACTOR
from src.errors.exceptions import ConflictError
from src.models import utcnow
from src.repositories.rotation.dr_window_repository import DrWindowRepository
from src.repositories.rotation.rotation_account_repository import RotationAccountRepository
from src.repositories.rotation.rotation_job_repository import RotationJobRepository
from src.services.audit.audit_service import AuditService

NOTE = "DR post-failover check (HA_DR.md §6.1)"


def _aware(t: datetime) -> datetime:
    return t if t.tzinfo else t.replace(tzinfo=UTC)


@dataclass
class ExportScan:
    accounts: set[uuid.UUID] = field(default_factory=set)
    lines: int = 0
    skipped: int = 0


def scan_export(lines: Iterable[str], since: datetime, until: datetime) -> ExportScan:
    """Accounts with non-verify rotation events in the window, from exported audit events."""
    scan = ExportScan()
    since, until = _aware(since), _aware(until)
    for raw in lines:
        if not raw.strip():
            continue
        scan.lines += 1
        try:
            event = json.loads(raw)
            action = str(event["action"])
            when = _aware(datetime.fromisoformat(str(event["occurred_at"])))
            details = event.get("details") or {}
            if not action.startswith("rotation.") or details.get("reason") == "verify":
                continue
            if since <= when <= until and details.get("account_id"):
                scan.accounts.add(uuid.UUID(str(details["account_id"])))
        except (KeyError, ValueError, TypeError, AttributeError):
            scan.skipped += 1
    return scan


@dataclass
class WindowAccount:
    account_id: uuid.UUID
    label: str
    from_db: bool
    from_export: bool
    known: bool


class DrFailoverService:
    def __init__(
        self,
        window: DrWindowRepository,
        jobs: RotationJobRepository,
        accounts: RotationAccountRepository,
        audit: AuditService,
    ) -> None:
        self._window = window
        self._jobs = jobs
        self._accounts = accounts
        self._audit = audit

    async def accounts_in_window(
        self, since: datetime, until: datetime, export: ExportScan | None
    ) -> list[WindowAccount]:
        db_ids = await self._window.rotated_in_window(_aware(since), _aware(until))
        export_ids = export.accounts if export else set()
        known = await self._window.existing(db_ids | export_ids)
        await self._window.rollback()
        out = []
        for aid in sorted(db_ids | export_ids, key=str):
            username, target = known.get(aid, ("?", "?"))
            out.append(
                WindowAccount(
                    aid, f"{username}@{target}", aid in db_ids, aid in export_ids, aid in known
                )
            )
        return out

    async def queue_verify(self, account: WindowAccount) -> tuple[uuid.UUID | None, str]:
        """A normal verify job; (job id, note). An open job is left to resume instead."""
        acc = await self._accounts.get(account.account_id)
        if acc is None:
            return None, "not in this database: re-onboard or reconcile by hand"
        try:
            job_id = await self._jobs.create(
                {
                    "account_id": acc.id,
                    "target_id": await self._accounts.target_id_of(acc.id),
                    "reason": VERIFY,
                    "status": PENDING,
                    "not_before": utcnow(),
                    "note": NOTE,
                }
            )
        except ConflictError:
            await self._jobs.rollback()
            open_job = await self._jobs.open_for_account(acc.id)
            await self._jobs.rollback()
            if open_job is not None:
                return open_job.id, f"open {open_job.reason} job resumes with its recovery rule"
            return None, "could not queue a verify"
        await self._audit.record(
            SYSTEM_ACTOR,
            "rotation.queued",
            object_type="rotation_job",
            object_id=job_id,
            safe_id=acc.safe_id,
            details={"account_id": str(acc.id), "reason": VERIFY, "dr_check": True},
        )
        await self._jobs.commit()
        return job_id, "verify queued"

    async def job_states(self, job_ids: list[uuid.UUID]) -> dict[uuid.UUID, str]:
        out = {}
        for jid in job_ids:
            job = await self._jobs.get(jid)
            if job is not None:
                out[jid] = job.status
        await self._jobs.rollback()
        return out

    @staticmethod
    def finished(status: str) -> bool:
        return status not in OPEN_STATES

    @staticmethod
    def verified(status: str) -> bool:
        return status == SUCCEEDED

    async def reconcile(self, account_id: uuid.UUID) -> str:
        """After a failed verify: queue a reconcile, or flag out of sync for manual action."""
        acc = await self._accounts.get(account_id)
        if acc is None:
            return "manual: account not in this database"
        if acc.reconcile_account_id is None:
            await self._accounts.update(acc.id, {"sync_status": OUT_OF_SYNC})
            await self._audit.record(
                SYSTEM_ACTOR,
                "rotation.out_of_sync",
                object_type="account",
                object_id=acc.id,
                safe_id=acc.safe_id,
                outcome="failure",
                details={"account_id": str(acc.id), "dr_check": True},
            )
            await self._accounts.commit()
            return "manual: no reconcile account; flagged out of sync"
        try:
            job_id = await self._jobs.create(
                {
                    "account_id": acc.id,
                    "target_id": await self._accounts.target_id_of(acc.id),
                    "reason": RECONCILE,
                    "status": PENDING,
                    "not_before": utcnow(),
                    "note": NOTE,
                }
            )
        except ConflictError:
            await self._jobs.rollback()
            return "manual: another job is open on this account"
        await self._accounts.update(acc.id, {"rotation_status": PENDING})
        await self._audit.record(
            SYSTEM_ACTOR,
            "rotation.queued",
            object_type="rotation_job",
            object_id=job_id,
            safe_id=acc.safe_id,
            details={"account_id": str(acc.id), "reason": RECONCILE, "dr_check": True},
        )
        await self._jobs.commit()
        return f"reconcile queued ({job_id})"

    async def audit_run(self, details: dict[str, Any], *, ok: bool) -> None:
        await self._audit.record(
            SYSTEM_ACTOR,
            "dr.post_failover_check",
            object_type="cluster",
            outcome="success" if ok else "failure",
            details=details,
        )
        await self._jobs.commit()
